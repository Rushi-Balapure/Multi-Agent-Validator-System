"""Contract tests for the SciFact BM25 index and independent gatherer."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from data.scifact_loader import load_manifest, snapshot_hash
from validator.retrieval.bm25 import build_index
from validator.retrieval.config import RetrievalConfig, load_retrieval_config
from validator.retrieval.errors import CorpusHashMismatch, RetrievalError
from validator.retrieval.models import EvidenceBundle, QueryHit, QueryLog, RetrievedPassage
from validator.retrieval.paths import REPO_ROOT
from validator.retrieve import (
    format_bundle_log,
    gather,
    load_claim_texts,
    main,
    resolve_gather_claim_ids,
    run_gather_claims,
    run_gather_dev10,
)
from validator.schemas import Evidence

DEV10 = [
    "scifact:0",
    "scifact:2",
    "scifact:4",
    "scifact:6",
    "scifact:9",
    "scifact:10",
    "scifact:11",
    "scifact:12",
    "scifact:14",
    "scifact:15",
]
PINNED_CORPUS_HASH = "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62"
REAL_CORPUS = REPO_ROOT / "data" / "raw" / "scifact" / "corpus.jsonl"
BANNED_GOLD_KEYS = {
    "gold_evidence",
    "gold_labels",
    "gold_citations",
    "cited_doc_ids",
    "asserted_answer",
    "conclusion",
    "conclusions",
    "same_evidence",
}


def corpus_doc(doc_id: int, sentence: str, title: str | None = None) -> dict:
    return {
        "doc_id": doc_id,
        "title": sentence if title is None else title,
        "abstract": [sentence],
        "structured": False,
    }


def write_corpus(directory: Path, docs: list[dict]) -> tuple[Path, str]:
    path = directory / "corpus.jsonl"
    lines = [
        json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for doc in docs
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def make_config(directory: Path, corpus_hash: str, **overrides) -> RetrievalConfig:
    corpus_yaml = directory / "corpus.yaml"
    corpus_yaml.write_text(
        "doc_id_scheme: scifact_s2orc_integer\n" f"corpus_hash: {corpus_hash}\n",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "scifact-bm25-gather-v1",
        "dataset": "scifact",
        "doc_id_scheme": "scifact_s2orc_integer",
        "corpus_config": str(corpus_yaml),
        "corpus_jsonl": str(directory / "corpus.jsonl"),
        "corpus_hash": corpus_hash,
        "claims_jsonl": str(directory / "claims.jsonl"),
        "development_manifest": str(directory / "manifest.json"),
        "index_path": str(directory / "index.json"),
        "k1": 1.5,
        "b": 0.75,
        "epsilon": 0.25,
        "top_k_per_query": 20,
        "max_passages": 8,
        "retrieval_round": 1,
        "tokenizer": "alnum_lower_v1",
        "rerank": "max_bm25",
        "query_templates": {
            "open_inquiry": "{text}",
            "scope_measurement": "{text} scope measurement",
            "limitations_null": "{text} limitations null results",
        },
        "fixed_claim_ids": list(DEV10),
    }
    payload.update(overrides)
    return RetrievalConfig.model_validate(payload)


def sample_passage(doc_id: int, **overrides) -> dict:
    text = f"passage {doc_id}"
    payload = {
        "doc_id": doc_id,
        "snapshot_hash": "ab" * 32,
        "text_span": text,
        "offsets": {"start": 0, "end": len(text), "sentence_idxs": [0]},
        "query": "query text",
        "rank": doc_id,
        "retrieval_round": 1,
        "provenance": "independent",
        "deduplication_group": f"s2orc:{doc_id}",
        "access_scope": "D1",
        "score": float(100 - doc_id),
    }
    payload.update(overrides)
    return payload


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def test_fixed_claim_ids_match_development_manifest_prefix():
    config = load_retrieval_config(REPO_ROOT / "configs" / "retrieval" / "scifact_bm25.yaml")
    manifest = load_manifest(REPO_ROOT / "manifests" / "scifact" / "scifact_development_v1.json")
    derived = [f"scifact:{native_id}" for native_id in manifest["ids"][:10]]
    assert list(config.fixed_claim_ids) == derived == DEV10
    corpus_yaml = yaml.safe_load(
        (REPO_ROOT / "configs" / "corpus" / "scifact.yaml").read_text(encoding="utf-8")
    )
    assert corpus_yaml["corpus_hash"] == config.corpus_hash == PINNED_CORPUS_HASH
    assert corpus_yaml["doc_id_scheme"] == "scifact_s2orc_integer"
    pin = json.loads((REPO_ROOT / "data" / "pins" / "scifact" / "PIN.json").read_text(encoding="utf-8"))
    assert pin["files"]["corpus.jsonl"]["sha256"] == PINNED_CORPUS_HASH
    loader = (REPO_ROOT / "data" / "scifact_loader.py").read_text(encoding="utf-8")
    assert 'claim_id=f"scifact:{native_id}"' in loader


def test_retrieval_sources_do_not_call_gold_loaders():
    paths = [REPO_ROOT / "src" / "validator" / "retrieve.py"]
    paths.extend(sorted((REPO_ROOT / "src" / "validator" / "retrieval").glob("*.py")))
    blob = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for banned in (
        "bundle_claim",
        "load_split",
        "gold_evidence",
        "gold_labels",
        "cited_doc_ids",
        "same_evidence",
    ):
        assert banned not in blob


def test_gather_signature_excludes_gold_inputs():
    signature = inspect.signature(gather)
    assert list(signature.parameters) == ["claim_or_neutral_question", "config", "claim_id"]
    assert not any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    assert BANNED_GOLD_KEYS.isdisjoint(signature.parameters)


@pytest.mark.parametrize("keyword", sorted(BANNED_GOLD_KEYS))
def test_gather_rejects_gold_keyword(keyword: str):
    with pytest.raises(TypeError):
        gather("alpha topic", object(), "scifact:2", **{keyword: [{"doc_id": 1}]})


def test_gather_rejects_bare_ids_and_record_payloads(tmp_path: Path):
    config = make_config(tmp_path, "ab" * 32)
    with pytest.raises(TypeError):
        gather({"claim": "alpha", "evidence": {"1": []}}, config, "scifact:2")
    with pytest.raises(TypeError):
        gather("alpha topic", config, 2)
    with pytest.raises(RetrievalError):
        gather("alpha topic", config, "2")
    with pytest.raises(ValueError):
        gather("   ", config, "scifact:2")


def test_retrieval_config_rejects_gold_field(tmp_path: Path):
    payload = make_config(tmp_path, "ab" * 32).model_dump()
    payload["gold_evidence"] = [{"doc_id": 1, "label": "SUPPORT"}]
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(payload)


def test_bundle_rejects_d0_and_over_caps():
    d0 = sample_passage(1, access_scope="D0")
    with pytest.raises(ValidationError):
        RetrievedPassage.model_validate(d0)
    original = sample_passage(1, provenance="original")
    with pytest.raises(ValidationError):
        RetrievedPassage.model_validate(original)
    Evidence.model_validate(
        {key: value for key, value in sample_passage(1).items() if key != "score"}
    )
    hits = [QueryHit(doc_id=i, rank=i, score=1.0) for i in range(1, 22)]
    with pytest.raises(ValidationError):
        QueryLog(form="open_inquiry", query="alpha", hits=hits)
    passages = [RetrievedPassage.model_validate(sample_passage(i)) for i in range(1, 10)]
    queries = [
        QueryLog(form="open_inquiry", query="alpha", hits=[]),
        QueryLog(form="scope_measurement", query="alpha scope", hits=[]),
        QueryLog(form="limitations_null", query="alpha limitations", hits=[]),
    ]
    with pytest.raises(ValidationError):
        EvidenceBundle(
            claim_id="scifact:2",
            query="alpha",
            queries=queries,
            retrieval_round=1,
            corpus_hash="ab" * 32,
            passages=passages,
        )


def test_index_build_refuses_corpus_hash_mismatch(tmp_path: Path):
    write_corpus(tmp_path, [corpus_doc(1, "alpha topic")])
    config = make_config(tmp_path, "0" * 64)
    sentinel = Path(config.index_path)
    sentinel.write_text("SENTINEL", encoding="utf-8")
    with pytest.raises(CorpusHashMismatch, match="refusing to index"):
        build_index(config)
    assert sentinel.read_text(encoding="utf-8") == "SENTINEL"


def test_index_build_is_reproducible_for_a_matching_hash(tmp_path: Path):
    docs = [
        corpus_doc(7, "zzzzuniquekinase measurement"),
        corpus_doc(3, "mitochondria background"),
    ]
    _path, digest = write_corpus(tmp_path, docs)
    config = make_config(tmp_path, digest)
    first = build_index(config)
    first_bytes = Path(config.index_path).read_bytes()
    second = build_index(config)
    assert Path(config.index_path).read_bytes() == first_bytes
    other = config.model_copy(update={"index_path": str(tmp_path / "other.json")})
    build_index(other)
    assert (tmp_path / "other.json").read_bytes() == first_bytes
    payload = json.loads(first_bytes)
    assert payload["corpus_hash"] == digest
    assert payload["doc_id_scheme"] == "scifact_s2orc_integer"
    assert payload["n_docs"] == 2
    assert [document["doc_id"] for document in payload["documents"]] == [3, 7]
    assert first.n_docs == second.n_docs == 2
    stored = {document["doc_id"]: document["snapshot_hash"] for document in payload["documents"]}
    for doc in docs:
        assert stored[doc["doc_id"]] == snapshot_hash(doc)


@pytest.mark.skipif(not REAL_CORPUS.is_file(), reason="pinned corpus is not downloaded")
def test_real_corpus_hash_mismatch_refuses_before_index(tmp_path: Path):
    config = load_retrieval_config(REPO_ROOT / "configs" / "retrieval" / "scifact_bm25.yaml")
    bad_hash = "0" * 64
    corpus_yaml = tmp_path / "corpus.yaml"
    corpus_yaml.write_text(
        "doc_id_scheme: scifact_s2orc_integer\n" f"corpus_hash: {bad_hash}\n",
        encoding="utf-8",
    )
    index_path = tmp_path / "should-not-exist.json"
    bad = config.model_copy(
        update={
            "corpus_hash": bad_hash,
            "corpus_config": str(corpus_yaml),
            "index_path": str(index_path),
        }
    )
    with pytest.raises(CorpusHashMismatch, match="refusing to index"):
        build_index(bad)
    assert not index_path.exists()


def test_gather_caps_top_k_and_passages(tmp_path: Path):
    docs = [corpus_doc(doc_id, f"alpha topic document {doc_id}") for doc_id in range(1, 26)]
    _path, digest = write_corpus(tmp_path, docs)
    config = make_config(tmp_path, digest, top_k_per_query=20, max_passages=8)
    bundle = gather("alpha topic", config, "scifact:2")
    assert bundle.claim_id == "scifact:2"
    assert bundle.query == "alpha topic"
    assert bundle.corpus_hash == digest
    assert bundle.retrieval_round == 1
    assert [item.form for item in bundle.queries] == [
        "open_inquiry",
        "scope_measurement",
        "limitations_null",
    ]
    assert bundle.queries[0].query == "alpha topic"
    for item in bundle.queries:
        assert len(item.hits) == 20
        assert [hit.rank for hit in item.hits] == list(range(1, 21))
    assert len(bundle.passages) == 8
    assert [passage.rank for passage in bundle.passages] == list(range(1, 9))
    assert len({passage.doc_id for passage in bundle.passages}) == 8
    for passage in bundle.passages:
        Evidence.model_validate(passage.model_dump(exclude={"score"}))
        assert passage.access_scope.value == "D1"
        assert passage.provenance.value == "independent"
        assert passage.deduplication_group == f"s2orc:{passage.doc_id}"
        assert passage.offsets is not None
        assert passage.offsets.start == 0
        assert passage.offsets.end == len(passage.text_span)
        scores = [
            hit.score
            for item in bundle.queries
            for hit in item.hits
            if hit.doc_id == passage.doc_id
        ]
        assert scores
        assert passage.score == max(scores)
    EvidenceBundle.model_validate_json(
        json.dumps(bundle.model_dump(mode="json"), sort_keys=True)
    )


def test_gather_dedupes_identical_abstracts(tmp_path: Path):
    docs = [
        corpus_doc(1, "zebraunique kinase measurement", title="zebraunique paper"),
        corpus_doc(2, "mitochondria background only"),
        corpus_doc(3, "zebraunique kinase measurement", title="other"),
    ]
    _path, digest = write_corpus(tmp_path, docs)
    config = make_config(tmp_path, digest)
    bundle = gather("zebraunique kinase", config, "scifact:4")
    assert [passage.doc_id for passage in bundle.passages] == [1]
    assert bundle.passages[0].text_span == "zebraunique kinase measurement"
    assert bundle.passages[0].snapshot_hash == snapshot_hash(docs[0])
    logged = {hit.doc_id for item in bundle.queries for hit in item.hits}
    assert 1 in logged
    assert 3 in logged
    assert 2 not in logged


def test_load_claim_texts_ignores_gold_fields(tmp_path: Path):
    claims_path = tmp_path / "claims.jsonl"
    record = {
        "id": 2,
        "claim": "alpha shared token 2",
        "evidence": {"123": [{"label": "SUPPORT", "sentences": [0]}]},
        "cited_doc_ids": [123],
        "asserted_answer": "supported",
        "conclusion": "GOLDCONCLUSIONSHOULDNOTLEAK",
    }
    claims_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    texts = load_claim_texts(["scifact:2"], claims_path)
    assert texts == {"scifact:2": "alpha shared token 2"}


def test_dev10_cli_writes_string_claim_ids_without_gold(tmp_path: Path):
    native_ids = [0, 2, 4, 6, 9, 10, 11, 12, 14, 15, 99]
    docs = [corpus_doc(doc_id, f"alpha shared token paper {doc_id}") for doc_id in range(1, 13)]
    _path, digest = write_corpus(tmp_path, docs)
    manifest = {"manifest_id": "test", "role": "development", "ids": native_ids}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    claim_lines = []
    for native_id in native_ids:
        claim_lines.append(
            json.dumps(
                {
                    "id": native_id,
                    "claim": f"alpha shared token {native_id}",
                    "evidence": {"123": [{"label": "SUPPORT", "sentences": [0]}]},
                    "cited_doc_ids": [123],
                    "asserted_answer": "supported",
                    "conclusion": "GOLDCONCLUSIONSHOULDNOTLEAK",
                }
            )
        )
    (tmp_path / "claims.jsonl").write_text("\n".join(claim_lines) + "\n", encoding="utf-8")
    config = make_config(tmp_path, digest)
    output = tmp_path / "dev10_bundles.jsonl"
    bundles = run_gather_dev10(config, output, download=False)
    assert [bundle.claim_id for bundle in bundles] == DEV10
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10
    for line, claim_id, native_id in zip(lines, DEV10, native_ids[:10], strict=True):
        payload = json.loads(line)
        assert payload["claim_id"] == claim_id
        assert payload["query"] == f"alpha shared token {native_id}"
        assert set(walk_keys(payload)).isdisjoint(BANNED_GOLD_KEYS)
        assert "GOLDCONCLUSIONSHOULDNOTLEAK" not in line
        assert "SUPPORT" not in line
        bundle = EvidenceBundle.model_validate(payload)
        assert len(bundle.passages) <= 8
        assert len(bundle.queries) == 3
        for item in bundle.queries:
            assert len(item.hits) <= 20
    swapped = config.model_copy(update={"fixed_claim_ids": list(reversed(DEV10))})
    with pytest.raises(RetrievalError, match="fixed_claim_ids"):
        run_gather_dev10(swapped, tmp_path / "other.jsonl", download=False)


def write_claims_manifest(tmp_path: Path, native_ids: list[int]) -> None:
    manifest = {"manifest_id": "test", "role": "development", "ids": native_ids}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    claim_lines = []
    for native_id in native_ids:
        claim_lines.append(
            json.dumps(
                {
                    "id": native_id,
                    "claim": f"alpha shared token {native_id}",
                    "evidence": {"123": [{"label": "SUPPORT", "sentences": [0]}]},
                    "cited_doc_ids": [123],
                    "asserted_answer": "supported",
                    "conclusion": "GOLDCONCLUSIONSHOULDNOTLEAK",
                }
            )
        )
    (tmp_path / "claims.jsonl").write_text("\n".join(claim_lines) + "\n", encoding="utf-8")


def test_default_gather_claim_ids_are_first_five_development_ids():
    config = load_retrieval_config(REPO_ROOT / "configs" / "retrieval" / "scifact_bm25.yaml")
    assert config.retrieval_round == 1
    assert config.rerank == "max_bm25"
    assert config.round2.enabled is False
    assert list(config.round2.start_when) == [
        "unresolved_question",
        "scope_mismatch",
        "contradictory_evidence",
    ]
    assert list(config.round2.stop_when) == [
        "exhausted_budget",
        "no_new_eligible_documents",
        "complete_bounded_evidence",
    ]
    assert config.rrf.enabled is False
    assert config.rrf.k == 60
    assert resolve_gather_claim_ids(config) == DEV10[:5]
    assert resolve_gather_claim_ids(config, limit=5) == DEV10[:5]


def test_round2_and_rrf_flags_reject_product_path():
    config = load_retrieval_config(REPO_ROOT / "configs" / "retrieval" / "scifact_bm25.yaml")
    payload = config.model_dump()
    payload["round2"] = {**payload["round2"], "enabled": True}
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(payload)
    payload = config.model_dump()
    payload["rrf"] = {**payload["rrf"], "enabled": True}
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(payload)
    payload = config.model_dump()
    payload["rrf"] = {**payload["rrf"], "k": 10}
    with pytest.raises(ValidationError):
        RetrievalConfig.model_validate(payload)


def test_gather_claims_five_development_ids(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    native_ids = [0, 2, 4, 6, 9, 10, 11, 12, 14, 15, 99]
    docs = [corpus_doc(doc_id, f"alpha shared token paper {doc_id}") for doc_id in range(1, 13)]
    _path, digest = write_corpus(tmp_path, docs)
    write_claims_manifest(tmp_path, native_ids)
    config = make_config(tmp_path, digest)
    selected = resolve_gather_claim_ids(config, limit=5)
    assert selected == DEV10[:5]
    output = tmp_path / "dev5_bundles.jsonl"
    bundles = run_gather_claims(config, output, selected, download=False)
    assert [bundle.claim_id for bundle in bundles] == DEV10[:5]
    assert len(bundles) == 5
    logged = capsys.readouterr().out
    lines = output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 5
    for line, claim_id, native_id in zip(lines, DEV10[:5], native_ids[:5], strict=True):
        payload = json.loads(line)
        assert payload["claim_id"] == claim_id
        assert payload["query"] == f"alpha shared token {native_id}"
        assert payload["retrieval_round"] == 1
        assert set(walk_keys(payload)).isdisjoint(BANNED_GOLD_KEYS)
        assert "GOLDCONCLUSIONSHOULDNOTLEAK" not in line
        assert "SUPPORT" not in line
        bundle = EvidenceBundle.model_validate(payload)
        assert len(bundle.passages) <= 8
        assert len(bundle.queries) == 3
        for item in bundle.queries:
            assert len(item.hits) <= 20
        log = format_bundle_log(bundle)
        assert f"claim_id={claim_id}" in log
        assert "form=open_inquiry" in log
        assert "hits=" in log
        assert "reranked=" in log
        assert log in logged
    arbitrary = run_gather_claims(
        config,
        tmp_path / "arbitrary.jsonl",
        ["scifact:15", "scifact:99"],
        download=False,
    )
    assert [bundle.claim_id for bundle in arbitrary] == ["scifact:15", "scifact:99"]
    assert all(len(bundle.passages) <= 8 for bundle in arbitrary)


def test_gather_claims_cli_limit_five(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    native_ids = [0, 2, 4, 6, 9, 10, 11, 12, 14, 15]
    docs = [corpus_doc(doc_id, f"alpha shared token paper {doc_id}") for doc_id in range(1, 13)]
    _path, digest = write_corpus(tmp_path, docs)
    write_claims_manifest(tmp_path, native_ids)
    config = make_config(tmp_path, digest)
    config_path = tmp_path / "retrieval.yaml"
    config_path.write_text(
        yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "data.pins.scifact.download_verify.ensure_scifact_raw",
        lambda _root: None,
    )
    output = tmp_path / "dev5_bundles.jsonl"
    code = main(
        [
            "gather-claims",
            "--config",
            str(config_path),
            "--limit",
            "5",
            "--output",
            str(output),
        ]
    )
    assert code == 0
    payloads = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [payload["claim_id"] for payload in payloads] == DEV10[:5]
    assert all(len(payload["passages"]) <= 8 for payload in payloads)
    assert all(set(walk_keys(payload)).isdisjoint(BANNED_GOLD_KEYS) for payload in payloads)
    code = main(
        [
            "gather-claims",
            "--config",
            str(config_path),
            "--claim-ids",
            "scifact:0,scifact:2",
            "--manifest",
            str(tmp_path / "manifest.json"),
        ]
    )
    assert code == 2
