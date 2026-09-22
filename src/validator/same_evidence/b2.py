"""B2-shaped same-evidence check: neutral question, isolated D0 reader, compare.

Named adaptation of research-plan baseline B2. This is not a reproduction of
MARCH or CoVe. The reader sees a template neutral question and shuffled D0
abstracts. It does not see ``asserted_answer``, gold rationales, or a separate
copy of the claim. The compare step then assigns SciFact ``SUPPORT``,
``REFUTE``, or ``NEI``. ``CONTRADICT`` is accepted only as an alias of
``REFUTE``. Four-way MAVS labels are rejected.

Dry-run / mock labels (no endpoint, no gold):

    material = newline join of
        seed,
        claim_id,
        neutral_question,
        claim,
        sealed reader answer,
        reader doc ids joined by commas
    label = ("SUPPORT", "REFUTE", "NEI")[sha256(material).digest()[0] % 3]

The sealed reader answer itself is:

    "mock-reader: evidence-only notes; n_docs={n}; digest={sha256(seed, question, doc ids)[:12]}"

or, when no abstracts were joined:

    "mock-reader: no D0 abstracts were attached; digest={...}"

Shuffle order is ``random.Random(int(sha256(f"{seed}:{claim_id}")[:16], 16))``
over passages that start in ``cited_doc_ids`` order. Mock labels do not read
annotated rationales. Instruction-text changes are recorded on ``prompt_hash``
and do not alter the mock formula.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Protocol

from .inputs import PredictInput

PREDICTION_LABELS = ("SUPPORT", "REFUTE", "NEI")
MOCK_LABEL_FORMULA = (
    "label = (SUPPORT, REFUTE, NEI)[sha256(utf-8 newline join of seed, claim_id, "
    "neutral_question, claim, sealed reader answer, comma-joined reader doc ids).digest()[0] % 3]. "
    "Reader answer is mock-reader with n_docs and a 12-hex digest of seed, question, and doc ids. "
    "Gold rationales are not inputs. CONTRADICT is not emitted by the mock; "
    "the live parser maps CONTRADICT to REFUTE."
)
_READER_KEYS = frozenset({"neutral_question", "evidence"})
_PASSAGE_KEYS = frozenset({"doc_id", "title", "abstract", "snapshot_hash"})
_COMPARE_KEYS = frozenset({"claim_id", "claim", "neutral_question", "sealed_reader"})
_SEALED_KEYS = frozenset({"answer", "cited_doc_ids"})
_FORBIDDEN_KEYS = frozenset(
    {
        "asserted_answer",
        "normalized_claim",
        "rationales",
        "gold_evidence_bundle",
        "sentences",
        "native_label_space",
        "label",
    }
)


class IsolationError(RuntimeError):
    """A reader or compare payload crossed the B2 information boundary."""


class LabelError(RuntimeError):
    """A model label was outside SciFact SUPPORT / REFUTE / NEI."""


class EndpointUnavailable(RuntimeError):
    """The local OpenAI-compatible endpoint could not be reached."""


class BaselineDataError(RuntimeError):
    """Configuration or model output cannot be used."""


def normalize_label(raw: str) -> str:
    """Map a model label onto SUPPORT, REFUTE, or NEI. CONTRADICT becomes REFUTE."""
    if not isinstance(raw, str):
        raise LabelError(f"label {raw!r} is not a string")
    token = raw.strip().upper()
    if token == "CONTRADICT":
        return "REFUTE"
    if token in PREDICTION_LABELS:
        return token
    raise LabelError(
        f"label {raw!r} is outside SciFact SUPPORT/REFUTE/NEI "
        "(CONTRADICT is accepted only as an alias of REFUTE)"
    )


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
_RFC1918_NETWORKS = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)


def _is_local_or_private_host(hostname: str | None) -> bool:
    """True for loopback names or an RFC1918 IPv4 literal. DNS names are not resolved."""
    if not hostname:
        return False
    host = hostname.lower()
    if host in _LOOPBACK_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if not isinstance(address, ipaddress.IPv4Address):
        return False
    return any(address in network for network in _RFC1918_NETWORKS)


def _is_local_or_private_endpoint(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    return _is_local_or_private_host(parsed.hostname)


def assert_local_or_private(base_url: str) -> None:
    """Allow loopback or an RFC1918 private host. Refuse public names and addresses.

    Permitted hosts are ``127.0.0.1``, ``localhost``, and IPv4 addresses in
    ``10.0.0.0/8``, ``172.16.0.0/12``, or ``192.168.0.0/16``. Other DNS names
    are refused without resolution, so a public name cannot pass by pointing
    at a private address. Redirects use the same rule.
    """
    if not _is_local_or_private_endpoint(base_url):
        raise BaselineDataError(
            f"refusing endpoint {base_url}; "
            "only loopback (127.0.0.1, localhost) and RFC1918 private addresses are allowed"
        )


def render_neutral_question(template: str, claim: str) -> str:
    """Fill the versioned question template. The claim appears only inside this question."""
    marker = "{claim}"
    if marker not in template:
        raise BaselineDataError("neutral-question template is missing the {claim} marker")
    rendered = template.replace(marker, claim).strip()
    if not rendered:
        raise BaselineDataError("neutral question rendered empty")
    return rendered


def _passage_rng(seed: int, claim_id: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{claim_id}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def shuffled_passages(item: PredictInput, seed: int) -> list[dict]:
    """D0 abstracts in seeded order, without rationales or labels."""
    passages = [
        {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "abstract": list(doc.abstract),
            "snapshot_hash": doc.snapshot_hash,
        }
        for doc in item.gold_evidence_bundle
    ]
    _passage_rng(seed, item.claim_id).shuffle(passages)
    return passages


def _walk_keys(value: object):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _reject_forbidden_keys(payload: dict, *, where: str) -> None:
    found = sorted(set(_walk_keys(payload)) & _FORBIDDEN_KEYS)
    if found:
        raise IsolationError(f"{where} payload contains forbidden keys {found}")


def assert_reader_isolated(payload: dict) -> None:
    """Reader inputs are the neutral question and D0 passage text only."""
    if set(payload) != _READER_KEYS:
        raise IsolationError(f"reader payload keys {sorted(payload)} are not the isolated reader view")
    question = payload["neutral_question"]
    if not isinstance(question, str) or not question.strip():
        raise IsolationError("reader payload is missing a neutral question")
    evidence = payload["evidence"]
    if not isinstance(evidence, list):
        raise IsolationError("reader evidence is not a list")
    for passage in evidence:
        if set(passage) != _PASSAGE_KEYS:
            raise IsolationError(
                f"reader passage keys {sorted(passage)} leak material beyond the abstract"
            )
    _reject_forbidden_keys(payload, where="reader")
    if "asserted_answer" in json.dumps(payload, ensure_ascii=False):
        raise IsolationError("reader payload contains asserted_answer")


def assert_compare_isolated(payload: dict) -> None:
    """Compare sees the claim and the sealed reader record, not gold rationales."""
    if set(payload) != _COMPARE_KEYS:
        raise IsolationError(f"compare payload keys {sorted(payload)} crossed the compare boundary")
    sealed = payload["sealed_reader"]
    if not isinstance(sealed, dict) or set(sealed) != _SEALED_KEYS:
        raise IsolationError("sealed reader record is missing or carries extra fields")
    _reject_forbidden_keys(payload, where="compare")


def reader_payload_for(item: PredictInput, template: str, seed: int) -> dict:
    payload = {
        "neutral_question": render_neutral_question(template, item.normalized_claim),
        "evidence": shuffled_passages(item, seed),
    }
    assert_reader_isolated(payload)
    return payload


def compare_payload_for(item: PredictInput, question: str, answer: str, cited_doc_ids: list[int]) -> dict:
    payload = {
        "claim_id": item.claim_id,
        "claim": item.normalized_claim,
        "neutral_question": question,
        "sealed_reader": {"answer": answer, "cited_doc_ids": list(cited_doc_ids)},
    }
    assert_compare_isolated(payload)
    return payload


def _mock_reader_digest(seed: int, question: str, doc_ids: list[int]) -> str:
    material = "\n".join([str(seed), question, ",".join(str(doc_id) for doc_id in doc_ids)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def mock_reader_answer(seed: int, question: str, doc_ids: list[int]) -> str:
    digest = _mock_reader_digest(seed, question, doc_ids)
    if doc_ids:
        return f"mock-reader: evidence-only notes; n_docs={len(doc_ids)}; digest={digest}"
    return f"mock-reader: no D0 abstracts were attached; digest={digest}"


def mock_compare_label(
    *,
    seed: int,
    claim_id: str,
    neutral_question: str,
    claim: str,
    reader_answer: str,
    doc_ids: list[int],
) -> str:
    """Deterministic SUPPORT / REFUTE / NEI. Gold rationales are not arguments."""
    material = "\n".join(
        [
            str(seed),
            claim_id,
            neutral_question,
            claim,
            reader_answer,
            ",".join(str(doc_id) for doc_id in doc_ids),
        ]
    )
    index = hashlib.sha256(material.encode("utf-8")).digest()[0] % 3
    return PREDICTION_LABELS[index]


def mock_rationale(label: str) -> str:
    return (
        f"mock-b2: {label} from sha256(seed, claim_id, neutral question, claim, "
        "sealed reader answer, reader doc ids) % 3; annotated evidence labels were not an input."
    )


def extract_json_object(text: str) -> dict:
    start = text.find("{")
    if start < 0:
        raise LabelError("model response did not contain a JSON object")
    try:
        value, _end = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise LabelError("model response JSON could not be parsed") from exc
    if not isinstance(value, dict):
        raise LabelError("model response JSON was not an object")
    return value


class InferenceClient(Protocol):
    inference_mode: str

    def read(self, payload: dict, system_prompt: str) -> tuple[str, list[int]]:
        """Return an evidence-only answer and the doc ids the reader cited."""

    def compare(self, payload: dict, system_prompt: str) -> tuple[str, str]:
        """Return a normalized label and a short rationale."""


class MockClient:
    """Offline stand-in. Does not open sockets or read gold rationales."""

    inference_mode = "mock"

    def __init__(self, seed: int) -> None:
        self.seed = seed

    def read(self, payload: dict, system_prompt: str) -> tuple[str, list[int]]:
        del system_prompt
        assert_reader_isolated(payload)
        doc_ids = [int(passage["doc_id"]) for passage in payload["evidence"]]
        answer = mock_reader_answer(self.seed, payload["neutral_question"], doc_ids)
        return answer, doc_ids

    def compare(self, payload: dict, system_prompt: str) -> tuple[str, str]:
        del system_prompt
        assert_compare_isolated(payload)
        sealed = payload["sealed_reader"]
        label = mock_compare_label(
            seed=self.seed,
            claim_id=payload["claim_id"],
            neutral_question=payload["neutral_question"],
            claim=payload["claim"],
            reader_answer=sealed["answer"],
            doc_ids=list(sealed["cited_doc_ids"]),
        )
        return label, mock_rationale(label)


class _LocalOrPrivateRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_local_or_private_endpoint(newurl):
            raise BaselineDataError(
                f"refusing redirect off the local or private-LAN endpoint to {newurl}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class OpenAICompatibleClient:
    """Chat client for an OpenAI-compatible loopback or private-LAN server.

    No API key is hardcoded. Public and cloud hosts are refused, including
    redirects that would leave the private network.
    """

    inference_mode = "endpoint"

    def __init__(self, *, base_url: str, model_id: str, temperature: float, timeout_seconds: float) -> None:
        assert_local_or_private(base_url)
        self.base_url = base_url.rstrip("/")
        self.model_id = model_id
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(_LocalOrPrivateRedirectHandler)

    def read(self, payload: dict, system_prompt: str) -> tuple[str, list[int]]:
        assert_reader_isolated(payload)
        body = self._chat(system_prompt, payload)
        parsed = extract_json_object(body)
        answer = parsed.get("answer")
        cited = parsed.get("cited_doc_ids")
        if not isinstance(answer, str) or not answer.strip():
            raise LabelError("reader response is missing answer text")
        if not isinstance(cited, list) or any(not isinstance(item, int) for item in cited):
            raise LabelError("reader response cited_doc_ids must be a list of integers")
        allowed = {int(passage["doc_id"]) for passage in payload["evidence"]}
        unknown = [item for item in cited if item not in allowed]
        if unknown:
            raise LabelError(f"reader cited doc ids that were not in D0: {unknown}")
        return answer.strip(), cited

    def compare(self, payload: dict, system_prompt: str) -> tuple[str, str]:
        assert_compare_isolated(payload)
        body = self._chat(system_prompt, payload)
        parsed = extract_json_object(body)
        rationale = parsed.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            raise LabelError("compare response is missing a rationale")
        return normalize_label(str(parsed.get("label", ""))), rationale.strip()

    def _chat(self, system_prompt: str, payload: dict) -> str:
        url = f"{self.base_url}/chat/completions"
        request_body = json.dumps(
            {
                "model": self.model_id,
                "temperature": self.temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    },
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=request_body,
            headers={"Content-Type": "application/json"},
        )
        api_key = _optional_api_key()
        if api_key:
            request.add_header("Authorization", f"Bearer {api_key}")
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            raise BaselineDataError(f"local endpoint returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise EndpointUnavailable(str(reason)) from exc
        try:
            parsed = json.loads(raw.decode("utf-8"))
            return parsed["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise BaselineDataError("local endpoint returned an unexpected chat payload") from exc


def _optional_api_key() -> str | None:
    import os

    value = os.environ.get("OPENAI_API_KEY")
    if value is None or not value.strip():
        return None
    return value.strip()


def run_b2(
    item: PredictInput,
    *,
    seed: int,
    neutral_template: str,
    reader_prompt: str,
    compare_prompt: str,
    client: InferenceClient,
) -> dict:
    """Run the three B2 stages for one joined claim."""
    if item.gold_evidence_bundle is None:
        raise IsolationError(f"{item.claim_id} is missing gold_evidence_bundle")
    reader_input = reader_payload_for(item, neutral_template, seed)
    answer, cited_doc_ids = client.read(reader_input, reader_prompt)
    question = reader_input["neutral_question"]
    compare_input = compare_payload_for(item, question, answer, cited_doc_ids)
    label, rationale = client.compare(compare_input, compare_prompt)
    label = normalize_label(label)
    if not isinstance(rationale, str) or not rationale.strip():
        raise LabelError(f"{item.claim_id} produced an empty rationale")
    return {
        "claim_id": item.claim_id,
        "label": label,
        "rationale": rationale.strip(),
        "adaptation": "B2",
        "system_id": "same_evidence_baseline",
        "neutral_question": question,
        "reader_answer": answer,
        "reader_cited_doc_ids": cited_doc_ids,
        "inference_mode": client.inference_mode,
    }
