"""CLI for B0 / B1 / B3 / O on a frozen claim-id file."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from validator.baselines.evidence import ADAPTATIONS
from validator.baselines.single_judge import MockSingleJudge, run_single_judge
from validator.claim_sample import ClaimSampleError, claim_ids_from_file
from validator.run_control import DEFAULT_MAX_WORKERS, run_items
from validator.same_evidence.b2 import (
    EndpointUnavailable,
    IsolationError,
    LabelError,
    OpenAICompatibleClient,
    apply_openai_env,
    assert_local_or_private,
    load_repo_dotenv,
)
from validator.same_evidence.inputs import (
    BaselineDataError,
    MissingEvidenceJoinError,
    PredictInput,
    load_split_inputs,
    repo_root,
    sha256_file,
    sha256_text,
)
from validator.same_evidence.runner import _failed_b2_row
from validator.schemas import ExecutionStatus, Run
from validator.split_policy import SplitPolicyError, assert_limit_for_split, assert_split_allowed
from validator.usage import UsageMeter, rates_from_env

SYSTEM_ID = "reference_baseline"


class OutputPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predictions: str
    run_sidecar: str


class BaselineJudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_id: Literal["reference_baseline"]
    adaptation: Literal["B0", "B1", "B3", "O"]
    adaptation_note: str = Field(min_length=1)
    split: Literal["development", "calibration", "held_out_local_eval"]
    limit: int = Field(ge=1)
    seed: int
    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    temperature: float
    timeout_seconds: float = Field(gt=0)
    dry_run: bool
    prompt: str
    corpus_config: str
    retrieval_config: str | None = None
    output: OutputPaths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reference baselines B0, B1, B3, O.")
    parser.add_argument("--config", required=True, help="Baseline YAML.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--claim-ids-file", default=None)
    parser.add_argument("--frozen-final", action="store_true")
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--run-sidecar", default=None)
    return parser.parse_args(argv)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_config(path: Path) -> BaselineJudgeConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise BaselineDataError(f"{path} is not a YAML mapping")
    try:
        return BaselineJudgeConfig.model_validate(raw)
    except ValidationError as exc:
        raise BaselineDataError(f"invalid baseline config {path}: {exc}") from exc


def _dry_run(args: argparse.Namespace, config: BaselineJudgeConfig) -> bool:
    if args.dry_run and args.live:
        raise BaselineDataError("pass only one of --dry-run and --live")
    if args.dry_run:
        return True
    if args.live:
        return False
    return config.dry_run


def _d1_for(item: PredictInput, root: Path, config: BaselineJudgeConfig):
    if config.adaptation != "B3":
        return None
    from validator.retrieval.config import load_retrieval_config
    from validator.retrieve import load_claim_texts
    from validator.runner import gather_bundle
    from validator.schemas import Claim, ClaimSource, SplitRole

    if not config.retrieval_config:
        raise BaselineDataError("B3 requires retrieval_config")
    retrieval = load_retrieval_config(_resolve(root, config.retrieval_config))
    texts = load_claim_texts([item.claim_id], retrieval.resolve(retrieval.claims_jsonl))
    claim = Claim(
        claim_id=item.claim_id,
        normalized_claim=item.normalized_claim,
        exact_source_span=item.normalized_claim,
        neutral_question=item.normalized_claim,
        source=ClaimSource(
            dataset="scifact",
            native_id=int(item.claim_id.split(":", 1)[1]),
            split_role=SplitRole(item.split_role),
        ),
    )
    return gather_bundle(claim, retrieval)


def execute(args: argparse.Namespace) -> None:
    root = repo_root()
    config_path = _resolve(root, args.config)
    config = load_config(config_path)
    if config.adaptation not in ADAPTATIONS:
        raise BaselineDataError(f"adaptation must be one of {ADAPTATIONS}")
    load_repo_dotenv(root)
    dry_run = _dry_run(args, config)
    base_url, model_id = config.base_url, config.model_id
    if not dry_run:
        base_url, model_id = apply_openai_env(base_url, model_id)
    assert_local_or_private(base_url)
    limit = assert_limit_for_split(
        config.split, config.limit if args.limit is None else args.limit
    )
    assert_split_allowed(
        config.split,
        frozen_final=bool(args.frozen_final),
        freeze_path=root / "docs" / "freeze.json",
        observed={"adaptation": config.adaptation, "method_id": config.adaptation},
    )
    claim_ids = None
    if args.claim_ids_file:
        claim_ids = claim_ids_from_file(_resolve(root, args.claim_ids_file), limit=limit)
    loaded = load_split_inputs(
        root,
        config.split,
        limit=limit,
        corpus_config=config.corpus_config,
        claim_ids=claim_ids,
    )
    prompt_path = _resolve(root, config.prompt)
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_hash = sha256_text(prompt)
    config_hash = sha256_file(config_path)
    prompt_rate, completion_rate = rates_from_env()
    meter = UsageMeter(prompt_usd_per_1m=prompt_rate, completion_usd_per_1m=completion_rate)
    if dry_run:
        client: Any = MockSingleJudge(config.seed)
    else:
        client = OpenAICompatibleClient(
            base_url=base_url,
            model_id=model_id,
            temperature=config.temperature,
            timeout_seconds=config.timeout_seconds,
            meter=meter,
        )
    predictions_path = _resolve(root, args.output or config.output.predictions)
    workers = 1 if dry_run else DEFAULT_MAX_WORKERS
    if args.workers is not None:
        workers = args.workers
    started = datetime.now(timezone.utc)

    def worker(item: PredictInput) -> dict:
        try:
            d1 = None if dry_run else _d1_for(item, root, config)
            if config.adaptation == "B3" and dry_run:
                return run_single_judge(
                    item, adaptation=config.adaptation, prompt=prompt, client=client, d1_bundle=None
                )
            return run_single_judge(
                item, adaptation=config.adaptation, prompt=prompt, client=client, d1_bundle=d1
            )
        except (EndpointUnavailable, IsolationError, LabelError, BaselineDataError) as exc:
            failed = _failed_b2_row(item, reason=str(exc), inference_mode=client.inference_mode)
            failed["adaptation"] = config.adaptation
            failed["method_id"] = config.adaptation
            failed["system_id"] = SYSTEM_ID
            return failed

    rows = run_items(
        loaded.inputs,
        worker,
        claim_id_of=lambda item: item.claim_id,
        output=predictions_path,
        resume=not args.no_resume,
        max_workers=workers,
        retries=0,
    )
    finished = datetime.now(timezone.utc)
    usage = meter.summary()
    run = Run(
        run_id=f"{config.adaptation.lower()}-{config.split}-s{config.seed}-n{len(rows)}-{config_hash[:12]}",
        question_id=None,
        split=config.split,
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
    schema = json.loads((root / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    payload = run.model_dump(mode="json")
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=str)
    if errors:
        raise BaselineDataError(f"run record failed schema: {errors[0].message}")
    sidecar = {
        "system_id": SYSTEM_ID,
        "adaptation": config.adaptation,
        "adaptation_note": config.adaptation_note.strip(),
        "inference_mode": client.inference_mode,
        "model_invoked": client.inference_mode == "live",
        "n_predictions": len(rows),
        "claim_ids": [row["claim_id"] for row in rows],
        "claim_ids_file": args.claim_ids_file,
        "input_source": loaded.input_source,
        "run": payload,
    }
    sidecar_path = _resolve(root, args.run_sidecar or config.output.run_sidecar)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} {config.adaptation} predictions to {predictions_path}")


def main(argv: list[str] | None = None) -> int:
    try:
        execute(parse_args(argv))
    except MissingEvidenceJoinError as exc:
        print(f"EVIDENCE JOIN MISSING: {exc}", file=sys.stderr)
        return 2
    except (BaselineDataError, SplitPolicyError, ClaimSampleError, LabelError) as exc:
        print(f"BASELINE FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
