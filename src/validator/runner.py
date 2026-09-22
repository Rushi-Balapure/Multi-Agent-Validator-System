"""Opt-in wiring from a report fixture to Retrieval Wing gather.

Retrieval Wing contract (use this; do not reimplement BM25 / index / RRF):

- CLI: ``PYTHONPATH=src python3 -m validator.retrieve gather-claims``
- API: ``gather(claim_text, config, claim_id)`` — claim text or neutral
  question only. No gold D0, asserted answers, or original citations.
- Bundles: ``provenance=independent``, ``access_scope=D1``, at most 8 passages.
- Config: ``configs/retrieval/scifact_bm25.yaml``

The default path is dry_run. It delegates to the fixture pipeline and uses
fixture EvidenceBundles that already match that shape. ``--gather`` is the
only live path: it calls the public gather API for claims that have no
fixture bundle. Pytest does not pass ``--gather``.

From the repository root::

    PYTHONPATH=src python3 -m validator.runner \\
        --fixture tests/fixtures/judgment/e2e_happy.json --dry-run

    PYTHONPATH=src python3 -m validator.retrieve gather-claims \\
        --config configs/retrieval/scifact_bm25.yaml \\
        --limit 5 \\
        --output artifacts/retrieval/dev5_bundles.jsonl

Eval predictions (``method_id=V``, ``predictions.jsonl`` and ``run.json``)
are written by ``python -m validator.validator_v``. This module stays the
one-report verdict CLI.
"""

from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

from validator.evidence_reader import IsolationError
from validator.fixture_pipeline import (
    PipelineError,
    load_report_fixture,
    main as fixture_main,
    run_report,
)
from validator.retrieval.errors import RetrievalError
from validator.retrieval.models import EvidenceBundle
from validator.schemas import Claim

DEFAULT_RETRIEVAL_CONFIG = Path("configs/retrieval/scifact_bm25.yaml")


def neutral_gather_text(claim: Claim) -> str:
    """Text passed to gather. Gold D0 and asserted answers are not included."""
    if claim.neutral_question is None or not claim.neutral_question.strip():
        raise PipelineError("gather requires a neutral question")
    question = claim.neutral_question.strip()
    if claim.asserted_answer and claim.asserted_answer in question:
        raise IsolationError("neutral question contains the asserted answer")
    return question


def gather_bundle(claim: Claim, config: object) -> EvidenceBundle:
    """Call ``gather(claim_text, config, claim_id)`` with the neutral question.

    This is the only D1 live hook. It does not build an index, score BM25, or
    fuse ranks. Tests do not call the real gatherer.
    """
    from validator.retrieval.config import RetrievalConfig
    from validator.retrieve import gather

    if not isinstance(config, RetrievalConfig):
        raise PipelineError("gather config must be a RetrievalConfig")
    params = list(inspect.signature(gather).parameters)
    if params != ["claim_or_neutral_question", "config", "claim_id"]:
        raise PipelineError(
            "Retrieval Wing gather signature drifted; expected "
            "gather(claim_or_neutral_question, config, claim_id)"
        )
    return gather(neutral_gather_text(claim), config, claim.claim_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run staged D0 union D1 judgment for a report fixture. "
            "The default is dry_run and uses fixture EvidenceBundles that match "
            "the Retrieval Wing shape (independent D1, at most 8 passages). "
            "--gather fills missing D1 bundles through gather(claim_text, config, claim_id) "
            f"with config {DEFAULT_RETRIEVAL_CONFIG}. "
            "The Retrieval Wing CLI is python -m validator.retrieve gather-claims. "
            "pytest does not pass --gather."
        )
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Use fixture bundles. This is the default.",
    )
    parser.add_argument(
        "--gather",
        action="store_true",
        help=(
            "Fill missing D1 bundles by calling gather with the neutral question. "
            "Refused when the fixture is marked dry_run. "
            "Does not reimplement retrieval; calls validator.retrieve.gather."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_RETRIEVAL_CONFIG,
        help=(
            "Retrieval YAML. Used only with --gather. "
            f"Default {DEFAULT_RETRIEVAL_CONFIG}."
        ),
    )
    args = parser.parse_args(argv)
    if args.gather and args.dry_run:
        parser.error("pass either --dry-run or --gather")
    if not args.gather:
        forwarded = ["--fixture", str(args.fixture), "--dry-run"]
        if args.output is not None:
            forwarded.extend(["--output", str(args.output)])
        return fixture_main(forwarded)

    try:
        report = load_report_fixture(args.fixture)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if report.dry_run:
        print("this fixture is marked dry_run and refuses live gather", file=sys.stderr)
        return 2
    from validator.retrieval.config import load_retrieval_config
    from validator.retrieval.paths import REPO_ROOT

    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    try:
        config = load_retrieval_config(config_path)
        verdict = run_report(
            report,
            dry_run=False,
            gather_fn=lambda claim: gather_bundle(claim, config),
        )
    except (PipelineError, IsolationError, RetrievalError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    text = verdict.model_dump_json(indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
