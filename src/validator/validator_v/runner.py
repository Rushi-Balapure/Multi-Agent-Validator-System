"""Batch runner for method_id V.

Writes Eval predictions for the staged D0 ∪ D1 pipeline. The scored ``label``
is the reconciled four-way judgment mapped by ``validator.validator_v.labels``:

- supported → SUPPORT
- contradicted → REFUTE
- unaddressed → NEI
- underdetermined → NEI

``label_4way`` keeps the four-way token. ``label`` is always SUPPORT, REFUTE,
or NEI. A development run judges at most 20 claims. Each report still stops
at the staged pipeline's per-report cap of 8.

The default path is offline. It runs fixture reports through
``fixture_pipeline.run_report`` (decompose or fixture claims, then fixture
EvidenceBundles) and records ``inference_mode=mock``. It does not open a
socket.

``--gather`` is opt-in. It loads the first ``--limit`` development claim
texts (manifest order, the same order as B2) and calls Retrieval Wing
``gather(neutral_question, config, claim_id)`` via ``validator.runner.gather_bundle``.
Gold D0, asserted answers, and original citations are not arguments. The
citation auditor receives an empty D0 list and fail-closes. ``--live`` calls
the local reader and judge; pytest does not pass it.

From the repository root::

    PYTHONPATH=src python3 -m validator.validator_v \\
        --config configs/validator_v/development.yaml \\
        --dry-run \\
        --output artifacts/validator_v/predictions.jsonl \\
        --run-sidecar artifacts/validator_v/run.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from validator.decompose import CLAIM_BUDGET
from validator.evidence_reader import IsolationError
from validator.fixture_pipeline import (
    ClaimE2EVerdict,
    JudgmentFixture,
    PipelineError,
    ReportJudgmentFixture,
    load_report_fixture,
    reconciled_judgment,
    run_fixture,
    run_report,
)
from validator.live_judgment import (
    EndpointPolicyError,
    LiveConfigError,
    LoadedLive,
    default_live_config,
    load_live_settings,
)
from validator.retrieval.errors import RetrievalError
from validator.runner import gather_bundle
from validator.same_evidence._repo import find_repo_root
from validator.schemas import (
    Claim,
    ClaimSource,
    EvidenceScope,
    ExecutionStatus,
    Run,
    SplitRole,
)
from validator.validator_v.labels import (
    FOUR_WAY_TO_NATIVE,
    LABEL_MAPPING_TEXT,
    SCORED_EVIDENCE_SCOPE,
    LabelMapError,
    map_four_way_label,
)

SYSTEM_ID = "validator_v"
METHOD_ID = "V"
DEVELOPMENT_CLAIM_BUDGET = 20
CORPUS_CONFIG = "configs/corpus/scifact.yaml"

_EXECUTION_TOKENS = {
    ExecutionStatus.COMPLETED: "ok",
    ExecutionStatus.FAILED: "failed",
    ExecutionStatus.TIMEOUT: "timeout",
}


class ValidatorVError(Exception):
    """The V batch could not be written."""

    def __init__(self, message: str, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class OutputPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions: str
    run_sidecar: str


class ValidatorVConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: Literal["validator_v"]
    method_id: Literal["V"]
    adaptation: Literal["V"]
    adaptation_note: str = Field(min_length=1)
    split: Literal["development"]
    limit: int = Field(ge=1, le=DEVELOPMENT_CLAIM_BUDGET)
    seed: int
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    temperature: float
    timeout_seconds: float = Field(gt=0)
    dry_run: bool
    prediction_label_space: Literal["scifact_SUPPORT_REFUTE_NEI"]
    four_way_label_space: Literal["mavs_four_way"]
    scored_evidence_scope: Literal["D0_union_D1"]
    retrieval_config: str = Field(min_length=1)
    neutral_question: str = Field(min_length=1)
    reports: list[str] = Field(min_length=1)
    output: OutputPaths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Stack V over a development budget of at most 20 claims and write "
            "predictions.jsonl plus run.json. The default is an offline fixture-report "
            "dry-run (inference_mode=mock). --gather calls Retrieval Wing "
            "gather(neutral_question, config, claim_id) with claim text only."
        )
    )
    parser.add_argument(
        "--config",
        default="configs/validator_v/development.yaml",
        help="Validator V YAML. Paths inside it are relative to the repository root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force the offline fixture-report path. Does not call gather or a model.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Call the local OpenAI-compatible reader and judge. "
            "Refused for a fixture marked dry_run. Not used by pytest."
        ),
    )
    parser.add_argument(
        "--gather",
        action="store_true",
        help=(
            "Judge the first --limit development claims. D1 comes from "
            "gather(neutral_question, config, claim_id). Gold D0 is not loaded."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=f"Override the config limit. Must be from 1 to {DEVELOPMENT_CLAIM_BUDGET}.",
    )
    parser.add_argument("--output", default=None, help="Predictions JSONL path.")
    parser.add_argument("--run-sidecar", default=None, help="Run metadata JSON path.")
    return parser.parse_args(argv)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def load_config(path: Path) -> ValidatorVConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValidatorVError(f"{path} is not a YAML mapping")
    try:
        return ValidatorVConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValidatorVError(f"invalid validator V config {path}: {exc}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _prompt_bundle_hash(texts: dict[str, str]) -> str:
    chunks: list[str] = []
    for name in sorted(texts):
        chunks.append(name)
        chunks.append(texts[name])
    return sha256_text("\n".join(chunks))


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _pinned_corpus_hash(root: Path) -> str:
    loaded = yaml.safe_load((root / CORPUS_CONFIG).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("corpus_hash"), str):
        raise ValidatorVError(f"{CORPUS_CONFIG} is missing corpus_hash")
    return loaded["corpus_hash"]


def _check_corpus_hash(found: str, pinned: str) -> None:
    if found != pinned:
        raise ValidatorVError(
            f"bundle corpus_hash {found} does not match {CORPUS_CONFIG} corpus_hash {pinned}"
        )


def native_execution_status(status: ExecutionStatus | None) -> str:
    """Map a judgment execution status onto the token Eval already accepts."""
    if status is None:
        return "failed"
    return _EXECUTION_TOKENS[status]


def prediction_row(
    verdict: ClaimE2EVerdict,
    *,
    inference_mode: Literal["mock", "live"],
) -> dict[str, Any]:
    """One JSONL row. ``label`` is native; ``label_4way`` is the reconciled four-way token."""
    four_way = verdict.reconciled.label
    try:
        native = map_four_way_label(four_way)
    except LabelMapError as exc:
        raise ValidatorVError(str(exc), exit_code=1) from exc
    row: dict[str, Any] = {
        "adaptation": METHOD_ID,
        "claim_id": verdict.claim_id,
        "d0_label_4way": verdict.d0.label,
        "d1_label_4way": verdict.d1.label,
        "evidence_scope": SCORED_EVIDENCE_SCOPE,
        "execution_status": native_execution_status(verdict.reconciled.execution_status),
        "inference_mode": inference_mode,
        "label": native,
        "label_4way": four_way,
        "method_id": METHOD_ID,
        "rationale_codes": list(verdict.reconciled.rationale_codes),
        "system_id": SYSTEM_ID,
    }
    if verdict.proposer_claim_id:
        row["proposer_claim_id"] = verdict.proposer_claim_id
    return row


def _mode(args: argparse.Namespace, config: ValidatorVConfig) -> Literal["fixture", "gather"]:
    if args.dry_run and (args.live or args.gather):
        raise ValidatorVError("pass only one of --dry-run and --gather/--live")
    if args.gather:
        return "gather"
    if args.dry_run or args.live:
        return "fixture"
    if config.dry_run:
        return "fixture"
    raise ValidatorVError(
        "config dry_run is false. Pass --dry-run for fixture reports or --gather for development claims."
    )


def _limit(args: argparse.Namespace, config: ValidatorVConfig) -> int:
    limit = config.limit if args.limit is None else args.limit
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > DEVELOPMENT_CLAIM_BUDGET:
        raise ValidatorVError(
            f"limit must be from 1 to {DEVELOPMENT_CLAIM_BUDGET} development claims"
        )
    return limit


def _per_report_budget(remaining: int) -> int:
    if remaining < 1:
        raise ValidatorVError("no claim budget remaining")
    return min(CLAIM_BUDGET, remaining)


def _fixture_hashes(fixture: ReportJudgmentFixture, pinned: str) -> None:
    for attachment in fixture.attachments:
        if attachment.d1_bundle is None:
            continue
        _check_corpus_hash(attachment.d1_bundle.corpus_hash, pinned)


def _rows_from_fixture_reports(
    root: Path,
    config: ValidatorVConfig,
    *,
    limit: int,
    inference_mode: Literal["mock", "live"],
    live: LoadedLive | None,
    client: Any,
    pinned: str,
) -> tuple[list[dict[str, Any]], bool]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    partial = False
    remaining = limit
    for relative in config.reports:
        if remaining == 0:
            break
        path = _resolve(root, relative)
        if not path.is_file():
            raise ValidatorVError(f"report fixture is missing: {path}")
        try:
            fixture = load_report_fixture(path)
        except ValidationError as exc:
            raise ValidatorVError(f"invalid report fixture {path}: {exc}") from exc
        _fixture_hashes(fixture, pinned)
        budget = _per_report_budget(remaining)
        if inference_mode == "live":
            if fixture.dry_run:
                raise ValidatorVError(
                    f"{path} is marked dry_run and refuses --live"
                )
            if live is None:
                raise ValidatorVError("--live requires loaded endpoint settings", exit_code=1)
            verdicts, report_partial = _live_verdicts(
                fixture,
                live,
                claim_budget=budget,
                client=client,
            )
        else:
            try:
                report = run_report(fixture, dry_run=True, claim_budget=budget)
            except (PipelineError, IsolationError, ValueError) as exc:
                raise ValidatorVError(str(exc), exit_code=1) from exc
            verdicts = list(report.claims)
            report_partial = report.partial
        if len(verdicts) > budget:
            raise ValidatorVError(
                f"{path} judged {len(verdicts)} claims; the remaining budget was {budget}",
                exit_code=1,
            )
        partial = partial or report_partial
        for verdict in verdicts:
            if verdict.claim_id in seen:
                raise ValidatorVError(f"duplicate claim_id {verdict.claim_id}")
            seen.add(verdict.claim_id)
            rows.append(prediction_row(verdict, inference_mode=inference_mode))
            remaining -= 1
            if remaining == 0:
                break
    return rows, partial


def _live_verdicts(
    fixture: ReportJudgmentFixture,
    live: LoadedLive,
    *,
    claim_budget: int,
    client: Any,
) -> tuple[list[ClaimE2EVerdict], bool]:
    """Same claim selection as ``run_report``, with the live reader and judge."""
    from validator.fixture_pipeline import _bind_claim, _claims_for_report

    try:
        raw_claims, unchecked, _report_id = _claims_for_report(fixture, claim_budget)
    except (PipelineError, ValueError) as exc:
        raise ValidatorVError(str(exc), exit_code=1) from exc
    if len(fixture.attachments) != len(raw_claims):
        raise ValidatorVError(
            f"attachments ({len(fixture.attachments)}) must match "
            f"claims to judge ({len(raw_claims)})",
            exit_code=1,
        )
    if len(raw_claims) > claim_budget:
        for claim in raw_claims[claim_budget:]:
            span = claim.exact_source_span or claim.normalized_claim
            if span not in unchecked:
                unchecked.append(span)
        raw_claims = raw_claims[:claim_budget]
        attachments = fixture.attachments[:claim_budget]
    else:
        attachments = list(fixture.attachments)
    id_map = {
        claim.claim_id: attachment.retrieval_claim_id
        for claim, attachment in zip(raw_claims, attachments, strict=True)
    }
    verdicts: list[ClaimE2EVerdict] = []
    for claim, attachment in zip(raw_claims, attachments, strict=True):
        if attachment.d1_bundle is None:
            raise ValidatorVError(
                f"{claim.claim_id} has no fixture D1 bundle. "
                "Pass --gather to retrieve D1. --live does not build an index."
            )
        bound, proposer_id = _bind_claim(claim, attachment.retrieval_claim_id, id_map)
        staged = run_fixture(
            JudgmentFixture(
                fixture_id=f"{fixture.fixture_id}:{bound.claim_id}",
                claim=bound,
                d0_evidence=list(attachment.d0_evidence),
                d1_bundle=attachment.d1_bundle,
            ),
            live=live,
            client=client,
        )
        by_scope = {item.evidence_scope: item for item in staged.judgments}
        d0 = by_scope[EvidenceScope.D0]
        d1 = by_scope[EvidenceScope.D1]
        verdicts.append(
            ClaimE2EVerdict(
                claim_id=bound.claim_id,
                proposer_claim_id=proposer_id,
                d0=d0,
                d1=d1,
                reconciled=reconciled_judgment(d0, d1),
                citation_flags=staged.citation_flags,
                reconciler_notes=staged.reconciler_notes,
                claim_card=staged.claim_card,
                sealed_reader=staged.sealed_reader,
            )
        )
    return verdicts, bool(unchecked)


def _neutral_template(root: Path, config: ValidatorVConfig) -> str:
    path = _resolve(root, config.neutral_question)
    if not path.is_file():
        raise ValidatorVError(f"neutral question template is missing: {path}")
    text = path.read_text(encoding="utf-8")
    if "{claim}" not in text:
        raise ValidatorVError(f"{path} must contain {{claim}}")
    return text


def _claim_from_text(claim_id: str, text: str, template: str) -> Claim:
    from validator.retrieve import native_id_from_claim_id

    question = template.replace("{claim}", text.strip())
    return Claim(
        claim_id=claim_id,
        normalized_claim=text.strip(),
        exact_source_span=text.strip(),
        neutral_question=question,
        asserted_answer=None,
        source=ClaimSource(
            dataset="scifact",
            native_id=native_id_from_claim_id(claim_id),
            split_role=SplitRole.DEVELOPMENT,
        ),
    )


def _rows_from_gather(
    root: Path,
    config: ValidatorVConfig,
    *,
    limit: int,
    inference_mode: Literal["mock", "live"],
    live: LoadedLive | None,
    client: Any,
    pinned: str,
) -> tuple[list[dict[str, Any]], bool]:
    from validator.retrieval.config import load_retrieval_config
    from validator.retrieve import load_claim_texts, resolve_gather_claim_ids

    retrieval_path = _resolve(root, config.retrieval_config)
    try:
        retrieval = load_retrieval_config(retrieval_path)
        claim_ids = resolve_gather_claim_ids(retrieval, limit=limit)
        texts = load_claim_texts(claim_ids, retrieval.resolve(retrieval.claims_jsonl))
    except (RetrievalError, OSError, ValueError) as exc:
        raise ValidatorVError(str(exc), exit_code=1) from exc
    if len(claim_ids) > DEVELOPMENT_CLAIM_BUDGET:
        raise ValidatorVError(
            f"gather selected {len(claim_ids)} claims; the development budget is {DEVELOPMENT_CLAIM_BUDGET}"
        )
    template = _neutral_template(root, config)
    rows: list[dict[str, Any]] = []
    for claim_id in claim_ids:
        claim = _claim_from_text(claim_id, texts[claim_id], template)
        try:
            bundle = gather_bundle(claim, retrieval)
        except (PipelineError, IsolationError, RetrievalError, ValueError) as exc:
            raise ValidatorVError(str(exc), exit_code=1) from exc
        _check_corpus_hash(bundle.corpus_hash, pinned)
        staged = run_fixture(
            JudgmentFixture(
                fixture_id=f"validator-v-gather:{claim.claim_id}",
                claim=claim,
                d0_evidence=[],
                d1_bundle=bundle,
            ),
            live=live,
            client=client,
        )
        by_scope = {item.evidence_scope: item for item in staged.judgments}
        d0 = by_scope[EvidenceScope.D0]
        d1 = by_scope[EvidenceScope.D1]
        verdict = ClaimE2EVerdict(
            claim_id=claim.claim_id,
            proposer_claim_id=None,
            d0=d0,
            d1=d1,
            reconciled=reconciled_judgment(d0, d1),
            citation_flags=staged.citation_flags,
            reconciler_notes=staged.reconciler_notes,
            claim_card=staged.claim_card,
            sealed_reader=staged.sealed_reader,
        )
        rows.append(prediction_row(verdict, inference_mode=inference_mode))
    return rows, False


def _validate_run(root: Path, run: Run) -> dict[str, Any]:
    payload = run.model_dump(mode="json")
    schema = json.loads((root / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
    if errors:
        raise ValidatorVError(
            f"run record failed mavs_run_record schema: {errors[0].message}",
            exit_code=1,
        )
    return payload


def _load_live(root: Path, config: ValidatorVConfig) -> LoadedLive:
    try:
        return load_live_settings(
            default_live_config(root),
            base_url=config.base_url,
            model_id=config.model_id,
            root=root,
        )
    except (EndpointPolicyError, LiveConfigError) as exc:
        raise ValidatorVError(str(exc)) from exc


def execute(args: argparse.Namespace, *, client: Any = None) -> None:
    root = find_repo_root()
    config_path = _resolve(root, args.config)
    if not config_path.is_file():
        raise ValidatorVError(f"config is missing: {config_path}")
    config = load_config(config_path)
    if config.system_id != SYSTEM_ID or config.method_id != METHOD_ID:
        raise ValidatorVError(f"system_id must be {SYSTEM_ID} and method_id must be {METHOD_ID}")
    source = _mode(args, config)
    limit = _limit(args, config)
    inference_mode: Literal["mock", "live"] = "live" if args.live else "mock"
    live = _load_live(root, config) if inference_mode == "live" else None
    pinned = _pinned_corpus_hash(root)
    started = datetime.now(timezone.utc)
    if source == "gather":
        rows, partial = _rows_from_gather(
            root,
            config,
            limit=limit,
            inference_mode=inference_mode,
            live=live,
            client=client,
            pinned=pinned,
        )
        input_source = "gather"
    else:
        rows, partial = _rows_from_fixture_reports(
            root,
            config,
            limit=limit,
            inference_mode=inference_mode,
            live=live,
            client=client,
            pinned=pinned,
        )
        input_source = "fixture_report"
    if not rows:
        raise ValidatorVError("no predictions were produced", exit_code=1)
    if len(rows) > DEVELOPMENT_CLAIM_BUDGET:
        raise ValidatorVError(
            f"refusing to write {len(rows)} predictions; budget is {DEVELOPMENT_CLAIM_BUDGET}"
        )
    modes = {row["inference_mode"] for row in rows}
    if modes != {inference_mode}:
        raise ValidatorVError(f"mixed inference_mode values: {sorted(modes)}", exit_code=1)
    finished = datetime.now(timezone.utc)
    prompt_texts = {
        "label_mapping": LABEL_MAPPING_TEXT,
        "neutral_question": _neutral_template(root, config),
    }
    if live is not None:
        prompt_texts["reader"] = live.reader_prompt
        prompt_texts["judge"] = live.judge_prompt
    prompt_hash = _prompt_bundle_hash(prompt_texts)
    config_hash = sha256_file(config_path)
    run = Run(
        run_id=(
            f"validator-v-{config.split}-s{config.seed}-n{len(rows)}-{config_hash[:12]}"
        ),
        question_id=None,
        split=config.split,
        seed=config.seed,
        model_id=config.model_id,
        model_revision=None,
        prompt_hash=prompt_hash,
        corpus_hash=pinned,
        config_hash=config_hash,
        timestamps={
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
        },
        tokens=None,
        status=ExecutionStatus.COMPLETED,
    )
    run_payload = _validate_run(root, run)
    sidecar = {
        "system_id": SYSTEM_ID,
        "method_id": METHOD_ID,
        "adaptation": config.adaptation,
        "adaptation_note": config.adaptation_note.strip(),
        "inference_mode": inference_mode,
        "model_invoked": inference_mode == "live",
        "prediction_label_space": config.prediction_label_space,
        "four_way_label_space": config.four_way_label_space,
        "label_mapping": dict(FOUR_WAY_TO_NATIVE),
        "scored_evidence_scope": SCORED_EVIDENCE_SCOPE,
        "input_source": input_source,
        "n_predictions": len(rows),
        "development_claim_budget": DEVELOPMENT_CLAIM_BUDGET,
        "partial": partial,
        "prompt_hash_canonical": (
            "sha256 of utf-8 prompt name and file text pairs, sorted by name, joined with newlines"
        ),
        "run": run_payload,
    }
    if sidecar["run"]["run_id"] != run.run_id:
        raise ValidatorVError("sidecar run_id drifted", exit_code=1)
    predictions_path = _resolve(root, args.output or config.output.predictions)
    sidecar_path = _resolve(root, args.run_sidecar or config.output.run_sidecar)
    prediction_text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    _write_atomic(predictions_path, prediction_text)
    _write_atomic(sidecar_path, json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {len(rows)} {config.split} predictions to {predictions_path} "
        f"method_id={METHOD_ID} inference_mode={inference_mode}"
    )
    print(
        f"run sidecar {sidecar_path} run_id={run.run_id} input_source={input_source}"
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        execute(args)
    except ValidatorVError as exc:
        print(f"VALIDATOR V FAILED: {exc}", file=sys.stderr)
        return exc.exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
