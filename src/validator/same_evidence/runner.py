"""Command-line runner for the same-evidence B2 dry-run.

From the repository root, after the pinned SciFact files are present:

    PYTHONPATH=src python3 -m validator.same_evidence.runner \\
        --config configs/baseline/same_evidence_b2.yaml \\
        --dry-run --limit 20 \\
        --output artifacts/same_evidence_b2/predictions.jsonl \\
        --run-sidecar artifacts/same_evidence_b2/run.json

``--dry-run`` uses the documented mock in ``b2.py`` and does not open a socket
(``inference_mode=mock``). The urllib OpenAI-compatible client is used only for
``--live`` (or when the config sets ``dry_run: false``); successful live runs
record ``inference_mode=live`` on each prediction row and in the run sidecar.
``base_url`` must be a loopback or RFC1918 private-LAN endpoint. The default
config points at LM Studio on this machine, ``http://127.0.0.1:1234/v1``, with
model id ``qwen2.5-coder-1.5b-instruct``. An RFC1918 address such as
``http://192.168.1.10:1234/v1`` is also allowed from another machine on the
private LAN. Loopback remains valid for a local proxy. Public DNS names and
non-private addresses are refused, including redirects. A missing D0 join
exits 2. An empty SciFact evidence object does not.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from validator.claim_sample import ClaimSampleError, claim_ids_from_file
from validator.run_control import DEFAULT_MAX_WORKERS, run_items
from validator.schemas import ExecutionStatus, Run
from validator.split_policy import SplitPolicyError, assert_limit_for_split, assert_split_allowed
from validator.usage import UsageMeter, rates_from_env

from .b2 import (
    MOCK_LABEL_FORMULA,
    BaselineDataError as ModelError,
    EndpointUnavailable,
    IsolationError,
    LabelError,
    MockClient,
    OpenAICompatibleClient,
    apply_openai_env,
    assert_local_or_private,
    load_repo_dotenv,
    run_b2,
)
from .inputs import (
    BaselineDataError,
    LoadedInputs,
    MissingEvidenceJoinError,
    load_split_inputs,
    repo_root,
    sha256_file,
    sha256_text,
)

SYSTEM_ID = "same_evidence_baseline"


class PromptPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    neutral_question: str
    reader: str
    compare: str


class OutputPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions: str
    run_sidecar: str


class BaselineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: Literal["same_evidence_baseline"]
    adaptation: Literal["B2"]
    adaptation_note: str = Field(min_length=1)
    split: Literal["development", "calibration", "held_out_local_eval"]
    limit: int = Field(ge=1)
    seed: int
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    temperature: float
    timeout_seconds: float = Field(gt=0)
    dry_run: bool
    mock_if_unavailable: bool
    native_label_space: Literal["scifact_SUPPORT_CONTRADICT"]
    prediction_label_space: Literal["scifact_SUPPORT_REFUTE_NEI"]
    corpus_config: str
    prompts: PromptPaths
    output: OutputPaths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Same-evidence B2 baseline (SciFact D0 only).")
    parser.add_argument(
        "--config",
        default="configs/baseline/same_evidence_b2.yaml",
        help="Baseline YAML. Paths inside it are relative to the repository root.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Force the documented offline mock.")
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Call the OpenAI-compatible loopback or private-LAN endpoint. "
            "Falls back to the mock only if configured."
        ),
    )
    parser.add_argument("--limit", type=int, default=None, help="Override the config limit.")
    parser.add_argument(
        "--split",
        default=None,
        choices=["development", "calibration", "held_out_local_eval"],
        help="Override the config split. held_out_local_eval needs --frozen-final.",
    )
    parser.add_argument(
        "--claim-ids-file",
        default=None,
        help="Frozen sample JSON (claim_ids). B2 and V must share the same file.",
    )
    parser.add_argument(
        "--frozen-final",
        action="store_true",
        help="Required to run held_out_local_eval. Must match docs/freeze.json.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=f"Bounded thread pool size (default 1 dry-run, {DEFAULT_MAX_WORKERS} live).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing predictions and rerun every claim.",
    )
    parser.add_argument("--output", default=None, help="Predictions JSONL path.")
    parser.add_argument("--run-sidecar", default=None, help="Run metadata JSON path.")
    return parser.parse_args(argv)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def load_config(path: Path) -> BaselineConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BaselineDataError(f"{path} is not a YAML mapping")
    try:
        return BaselineConfig.model_validate(raw)
    except ValidationError as exc:
        raise BaselineDataError(f"invalid baseline config {path}: {exc}") from exc


def _prompt_bundle_hash(texts: dict[str, str]) -> str:
    """SHA-256 of prompt name and file text, sorted by name, joined with newlines."""
    chunks: list[str] = []
    for name in sorted(texts):
        chunks.append(name)
        chunks.append(texts[name])
    return sha256_text("\n".join(chunks))


def _load_prompts(root: Path, config: BaselineConfig) -> dict[str, str]:
    paths = {
        "neutral_question": _resolve(root, config.prompts.neutral_question),
        "reader": _resolve(root, config.prompts.reader),
        "compare": _resolve(root, config.prompts.compare),
    }
    texts: dict[str, str] = {}
    for name, path in paths.items():
        if not path.is_file():
            raise BaselineDataError(f"prompt file is missing: {path}")
        texts[name] = path.read_text(encoding="utf-8")
    return texts


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _load_inputs(
    root: Path,
    config: BaselineConfig,
    limit: int,
    claim_ids: list[str] | None,
) -> LoadedInputs:
    return load_split_inputs(
        root,
        config.split,
        limit=limit,
        corpus_config=config.corpus_config,
        claim_ids=claim_ids,
    )


def _resolve_claim_ids(root: Path, args: argparse.Namespace, limit: int) -> list[str] | None:
    if args.claim_ids_file is None:
        return None
    path = _resolve(root, args.claim_ids_file)
    try:
        return claim_ids_from_file(path, limit=limit)
    except ClaimSampleError as exc:
        raise BaselineDataError(str(exc)) from exc


def _failed_b2_row(item, *, reason: str, inference_mode: str) -> dict:
    return {
        "claim_id": item.claim_id,
        "label": "NEI",
        "rationale": f"fail-closed: {reason}",
        "adaptation": "B2",
        "system_id": SYSTEM_ID,
        "neutral_question": None,
        "reader_answer": None,
        "reader_cited_doc_ids": [],
        "inference_mode": inference_mode,
        "execution_status": "failed",
    }


def _dry_run(args: argparse.Namespace, config: BaselineConfig) -> bool:
    if args.dry_run and args.live:
        raise BaselineDataError("pass only one of --dry-run and --live")
    if args.dry_run:
        return True
    if args.live:
        return False
    return config.dry_run


def _validate_run(root: Path, run: Run) -> dict:
    payload = run.model_dump(mode="json")
    schema = json.loads((root / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
    if errors:
        raise BaselineDataError(f"run record failed mavs_run_record schema: {errors[0].message}")
    return payload


def execute(args: argparse.Namespace) -> None:
    root = repo_root()
    config_path = _resolve(root, args.config)
    config = load_config(config_path)
    if args.split is not None:
        config = config.model_copy(update={"split": args.split})
    if config.system_id != SYSTEM_ID:
        raise BaselineDataError(f"system_id must be {SYSTEM_ID}")
    load_repo_dotenv(root)
    dry_run = _dry_run(args, config)
    base_url, model_id = config.base_url, config.model_id
    if not dry_run:
        base_url, model_id = apply_openai_env(base_url, model_id)
    assert_local_or_private(base_url)
    try:
        limit = assert_limit_for_split(
            config.split, config.limit if args.limit is None else args.limit
        )
        assert_split_allowed(
            config.split,
            frozen_final=bool(args.frozen_final),
            freeze_path=root / "docs" / "freeze.json",
        )
    except SplitPolicyError as exc:
        raise BaselineDataError(str(exc)) from exc
    claim_ids = _resolve_claim_ids(root, args, limit)
    loaded = _load_inputs(root, config, limit, claim_ids)
    if claim_ids is None and len(loaded.inputs) != limit and loaded.input_source == "corpus_lock":
        raise BaselineDataError(
            f"expected {limit} {config.split} claims, joined {len(loaded.inputs)}"
        )
    prompt_texts = _load_prompts(root, config)
    prompt_hash = _prompt_bundle_hash(prompt_texts)
    config_hash = sha256_file(config_path)
    try:
        assert_split_allowed(
            config.split,
            frozen_final=bool(args.frozen_final),
            freeze_path=root / "docs" / "freeze.json",
            observed={
                "model_id": model_id,
                "config_hash": config_hash,
                "prompt_hash": prompt_hash,
                "corpus_hash": loaded.corpus_hash,
                "adaptation": config.adaptation,
                "method_id": config.adaptation,
            },
        )
    except SplitPolicyError as exc:
        raise BaselineDataError(str(exc)) from exc
    started = datetime.now(timezone.utc)
    prompt_rate, completion_rate = rates_from_env()
    meter = UsageMeter(prompt_usd_per_1m=prompt_rate, completion_usd_per_1m=completion_rate)
    client: MockClient | OpenAICompatibleClient
    if dry_run:
        client = MockClient(config.seed)
    else:
        client = OpenAICompatibleClient(
            base_url=base_url,
            model_id=model_id,
            temperature=config.temperature,
            timeout_seconds=config.timeout_seconds,
            meter=meter,
        )
    predictions_path = _resolve(root, args.output or config.output.predictions)
    workers = 1 if dry_run else (args.workers if args.workers is not None else DEFAULT_MAX_WORKERS)
    if args.workers is not None:
        workers = args.workers
        if workers < 1:
            raise BaselineDataError("workers must be at least 1")

    def worker(item):
        try:
            return run_b2(
                item,
                seed=config.seed,
                neutral_template=prompt_texts["neutral_question"],
                reader_prompt=prompt_texts["reader"],
                compare_prompt=prompt_texts["compare"],
                client=client,
            )
        except EndpointUnavailable as exc:
            if not config.mock_if_unavailable:
                return _failed_b2_row(item, reason=str(exc), inference_mode="live")
            # First-claim mock fallback stays sequential-only.
            raise
        except (ModelError, IsolationError, LabelError) as exc:
            return _failed_b2_row(
                item,
                reason=str(exc),
                inference_mode=client.inference_mode,
            )

    try:
        rows = run_items(
            loaded.inputs,
            worker,
            claim_id_of=lambda item: item.claim_id,
            output=predictions_path,
            resume=not args.no_resume,
            max_workers=workers,
            retries=0,
        )
    except EndpointUnavailable as exc:
        if not config.mock_if_unavailable:
            raise ModelError(f"local endpoint unavailable ({exc}).") from exc
        print(
            f"local endpoint unavailable ({exc}); using the documented mock",
            file=sys.stderr,
        )
        client = MockClient(config.seed)
        rows = run_items(
            loaded.inputs,
            lambda item: run_b2(
                item,
                seed=config.seed,
                neutral_template=prompt_texts["neutral_question"],
                reader_prompt=prompt_texts["reader"],
                compare_prompt=prompt_texts["compare"],
                client=client,
            ),
            claim_id_of=lambda item: item.claim_id,
            output=predictions_path,
            resume=False,
            max_workers=1,
            retries=0,
        )
    finished = datetime.now(timezone.utc)
    mode = client.inference_mode
    if len(rows) != len(loaded.inputs):
        raise BaselineDataError("prediction count does not match the joined claims")
    run_split = loaded.split_role
    usage = meter.summary()
    run = Run(
        run_id=f"same-evidence-b2-{run_split}-s{config.seed}-n{len(rows)}-{config_hash[:12]}",
        question_id=None,
        split=run_split,
        seed=config.seed,
        model_id=model_id,
        model_revision=None,
        prompt_hash=prompt_hash,
        corpus_hash=loaded.corpus_hash,
        config_hash=config_hash,
        timestamps={
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "latency_seconds": usage["latency_seconds"],
        },
        tokens=usage,
        status=ExecutionStatus.COMPLETED,
    )
    run_payload = _validate_run(root, run)
    sidecar = {
        "system_id": SYSTEM_ID,
        "adaptation": config.adaptation,
        "adaptation_note": config.adaptation_note.strip(),
        "inference_mode": mode,
        "model_invoked": mode == "live",
        "mock_label_formula": MOCK_LABEL_FORMULA if mode == "mock" else None,
        "prediction_label_space": config.prediction_label_space,
        "native_label_space": config.native_label_space,
        "input_source": loaded.input_source,
        "n_predictions": len(rows),
        "n_failed": sum(1 for row in rows if row.get("execution_status") == "failed"),
        "claim_ids": [row["claim_id"] for row in rows],
        "claim_ids_file": args.claim_ids_file,
        "n_nei_eligible_empty_evidence": sum(1 for item in loaded.inputs if item.nei_eligible()),
        "prompt_hash_canonical": (
            "sha256 of utf-8 prompt name and file text pairs, sorted by name, joined with newlines"
        ),
        "prompt_files": {
            name: {
                "path": getattr(config.prompts, name),
                "sha256": sha256_text(text),
            }
            for name, text in prompt_texts.items()
        },
        "run": run_payload,
    }
    predictions_path = _resolve(root, args.output or config.output.predictions)
    sidecar_path = _resolve(root, args.run_sidecar or config.output.run_sidecar)
    prediction_text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
    )
    _write_atomic(predictions_path, prediction_text)
    _write_atomic(sidecar_path, json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n")
    n_empty = sidecar["n_nei_eligible_empty_evidence"]
    print(f"wrote {len(rows)} {run_split} predictions to {predictions_path}")
    print(
        f"empty annotated evidence (NEI-eligible, not join failures): {n_empty}"
    )
    print(f"run sidecar {sidecar_path} system_id={SYSTEM_ID} inference_mode={mode}")


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        execute(args)
    except MissingEvidenceJoinError as exc:
        print(f"EVIDENCE JOIN MISSING: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (
        BaselineDataError,
        ModelError,
        IsolationError,
        LabelError,
        EndpointUnavailable,
        ClaimSampleError,
        SplitPolicyError,
    ) as exc:
        print(f"BASELINE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
