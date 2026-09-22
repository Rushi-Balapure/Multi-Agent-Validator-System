"""Pure-Python Okapi BM25 over the pinned SciFact abstract corpus.

``rank_bm25`` is not a dependency: it imports numpy. Scoring matches
``BM25Okapi`` from that library (Trotman et al.):

    idf(t) = log(N - df + 0.5) - log(df + 0.5)

Negative idf values are replaced with ``epsilon * average_idf`` (epsilon 0.25).
``k1`` 1.5 and ``b`` 0.75. Query-term frequency is repeated addition of the
document term, the same way ``BM25Okapi.get_scores`` walks the token list.

Tokens are ASCII ``[a-z0-9]+`` after ``str.lower``. No stemmer, so the index
does not depend on a stemmer version. Title tokens are indexed; the stored
passage is the abstract span from the corpus-lock loader.

TODO: dense retrieval and reciprocal-rank fusion (``1 / (60 + rank)`` summed
across lists) are a later development comparison, not this index.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

from validator.retrieval.config import RetrievalConfig, verify_corpus_lock
from validator.retrieval.errors import RetrievalError

INDEX_VERSION = "scifact-bm25-v1"
_TOKEN = re.compile(r"[a-z0-9]+")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")

_INDEX_CACHE: dict[tuple, BM25Index] = {}


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def canonical_index_json(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def _idf_table(n_docs: int, df: dict[str, int], epsilon: float) -> dict[str, float]:
    if n_docs <= 0:
        raise RetrievalError("cannot compute idf for an empty corpus")
    if not df:
        return {}
    idf: dict[str, float] = {}
    total = 0.0
    negative: list[str] = []
    for term in sorted(df):
        freq = df[term]
        value = math.log(n_docs - freq + 0.5) - math.log(freq + 0.5)
        idf[term] = value
        total += value
        if value < 0:
            negative.append(term)
    average = total / len(idf)
    floor = epsilon * average
    for term in negative:
        idf[term] = floor
    return idf


class BM25Index:
    """In-memory postings built from a canonical index payload."""

    def __init__(self, payload: dict) -> None:
        self.index_version = payload["index_version"]
        self.corpus_hash = payload["corpus_hash"]
        self.doc_id_scheme = payload["doc_id_scheme"]
        self.tokenizer = payload["tokenizer"]
        self.k1 = float(payload["k1"])
        self.b = float(payload["b"])
        self.epsilon = float(payload["epsilon"])
        documents = payload["documents"]
        if payload["n_docs"] != len(documents):
            raise RetrievalError("index n_docs does not match the document list")
        if not documents:
            raise RetrievalError("refusing to load an empty BM25 index")
        self.doc_ids: list[int] = []
        self.doc_len: list[int] = []
        self.snapshot_by_id: dict[int, str] = {}
        self.postings: dict[str, list[tuple[int, int]]] = {}
        for doc_index, document in enumerate(documents):
            doc_id = document["doc_id"]
            if not isinstance(doc_id, int) or isinstance(doc_id, bool):
                raise RetrievalError("index doc_id must be an integer")
            digest = document["snapshot_hash"]
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise RetrievalError(f"index snapshot_hash for doc_id {doc_id} is not sha256")
            tf = document["tf"]
            if not isinstance(tf, dict):
                raise RetrievalError(f"index tf for doc_id {doc_id} is not an object")
            length = document["token_length"]
            if length != sum(tf.values()):
                raise RetrievalError(f"index token_length drift for doc_id {doc_id}")
            if doc_id in self.snapshot_by_id:
                raise RetrievalError(f"duplicate doc_id {doc_id} in the index")
            self.doc_ids.append(doc_id)
            self.doc_len.append(length)
            self.snapshot_by_id[doc_id] = digest
            for term, freq in tf.items():
                if not isinstance(term, str) or not isinstance(freq, int) or freq < 1:
                    raise RetrievalError(f"invalid postings for doc_id {doc_id}")
                self.postings.setdefault(term, []).append((doc_index, freq))
        if self.doc_ids != sorted(self.doc_ids):
            raise RetrievalError("index documents must be sorted by doc_id")
        df = {term: len(postings) for term, postings in self.postings.items()}
        self.idf = _idf_table(len(documents), df, self.epsilon)
        self.avgdl = sum(self.doc_len) / len(self.doc_len)

    @property
    def n_docs(self) -> int:
        return len(self.doc_ids)

    def matches(self, config: RetrievalConfig) -> bool:
        return (
            self.index_version == INDEX_VERSION
            and self.corpus_hash == config.corpus_hash
            and self.doc_id_scheme == config.doc_id_scheme
            and self.tokenizer == config.tokenizer
            and self.k1 == config.k1
            and self.b == config.b
            and self.epsilon == config.epsilon
        )

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Return ``(doc_id, score)`` sorted by descending score, then doc_id.

        The list is at most ``top_k`` documents. Documents with no query token
        stay at score 0 and can appear only when fewer positive scores exist;
        callers drop non-positive scores so the top 20 are not padded.
        """
        if top_k < 1:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        scores = [0.0] * self.n_docs
        k1 = self.k1
        b = self.b
        avgdl = self.avgdl if self.avgdl else 1.0
        for token in tokens:
            postings = self.postings.get(token)
            if not postings:
                continue
            idf = self.idf.get(token, 0.0)
            for doc_index, freq in postings:
                norm = 1.0 - b + b * self.doc_len[doc_index] / avgdl
                denom = freq + k1 * norm
                scores[doc_index] += idf * (freq * (k1 + 1.0) / denom)
        order = sorted(range(self.n_docs), key=lambda i: (-scores[i], self.doc_ids[i]))
        return [(self.doc_ids[i], scores[i]) for i in order[:top_k]]

    @classmethod
    def from_payload(cls, payload: dict) -> BM25Index:
        if payload.get("index_version") != INDEX_VERSION:
            raise RetrievalError(
                f"index_version {payload.get('index_version')!r} is not {INDEX_VERSION}"
            )
        return cls(payload)

    @classmethod
    def load(cls, path: Path) -> BM25Index:
        return cls.from_payload(json.loads(path.read_text(encoding="utf-8")))


def _document_record(doc: dict) -> dict:
    from data.scifact_loader import abstract_text_and_spans, snapshot_hash

    abstract, _spans = abstract_text_and_spans(doc["abstract"])
    title = doc.get("title") or ""
    if not isinstance(title, str):
        raise RetrievalError(f"doc_id {doc.get('doc_id')} title is not a string")
    tokens = tokenize(f"{title} {abstract}")
    tf = dict(sorted(Counter(tokens).items()))
    return {
        "doc_id": doc["doc_id"],
        "snapshot_hash": snapshot_hash(doc),
        "token_length": len(tokens),
        "tf": tf,
    }


def build_index(config: RetrievalConfig) -> BM25Index:
    """Verify the pinned corpus hash, then write a canonical BM25 index.

    Hash verification happens before the corpus is parsed and before the index
    path is opened for writing.
    """
    from data.scifact_loader import load_corpus

    verify_corpus_lock(config)
    corpus_path = config.resolve(config.corpus_jsonl)
    corpus = load_corpus(corpus_path.parent)
    if not corpus:
        raise RetrievalError("refusing to index an empty corpus")
    documents = [_document_record(corpus[doc_id]) for doc_id in sorted(corpus)]
    payload = {
        "b": config.b,
        "corpus_hash": config.corpus_hash,
        "doc_id_scheme": config.doc_id_scheme,
        "documents": documents,
        "epsilon": config.epsilon,
        "index_version": INDEX_VERSION,
        "k1": config.k1,
        "n_docs": len(documents),
        "tokenizer": config.tokenizer,
    }
    path = config.resolve(config.index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = canonical_index_json(payload)
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(serialized, encoding="utf-8")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    print(
        f"indexed n_docs={len(documents)} corpus_hash={config.corpus_hash} index_path={path}",
        flush=True,
    )
    return BM25Index.from_payload(payload)


def ensure_index(config: RetrievalConfig) -> BM25Index:
    """Load an index when its hash and BM25 parameters match; otherwise build one."""
    verify_corpus_lock(config)
    path = config.resolve(config.index_path)
    if path.is_file():
        stat = path.stat()
        key = (
            str(path),
            stat.st_mtime_ns,
            stat.st_size,
            config.corpus_hash,
            config.k1,
            config.b,
            config.epsilon,
            config.tokenizer,
            config.doc_id_scheme,
        )
        cached = _INDEX_CACHE.get(key)
        if cached is not None:
            return cached
        loaded = BM25Index.load(path)
        if loaded.matches(config):
            _INDEX_CACHE[key] = loaded
            return loaded
    index = build_index(config)
    stat = path.stat()
    key = (
        str(path),
        stat.st_mtime_ns,
        stat.st_size,
        config.corpus_hash,
        config.k1,
        config.b,
        config.epsilon,
        config.tokenizer,
        config.doc_id_scheme,
    )
    _INDEX_CACHE[key] = index
    return index
