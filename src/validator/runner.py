"""Opt-in wiring from a report fixture to Retrieval Wing gather.

The default is dry_run. It delegates to the fixture pipeline and does not
build an index. ``--gather`` calls the public gather API with the neutral
question only, and only for claims that have no fixture bundle.

From the repository root::

    PYTHONPATH=src python3 -m validator.runner \\
        --fixture tests/fixtures/judgment/e2e_happy.json --dry-run

``--gather`` is not used by pytest. A fixture marked ``dry_run`` refuses it.
"""

from __future__ import annotations

import argparse
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


def neutral_gather_text(claim: Claim) -> str:
    """Text passed to gather. The asserted answer is not included."""
    if claim.neutral_question is None or not claim.neutral_question.strip():
        raise PipelineError("gather requires a neutral question")
    question = claim.neutral_question.strip()
    if claim.asserted_answer and claim.asserted_answer in question:
        raise IsolationError("neutral question contains the asserted answer")
    return question


def gather_bundle(claim: Claim, config: object) -> EvidenceBundle:
    """Call ``gather(neutral_question, config, claim_id)``. Tests do not use this."""
    from validator.retrieval.config import RetrievalConfig
    from validator.retrieve import gather

    if not isinstance(config, RetrievalConfig):
        raise PipelineError("gather config must be a RetrievalConfig")
    return gather(neutral_gather_text(claim), config, claim.claim_id)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run staged D0 union D1 judgment for a report fixture. "
            "The default is dry_run and uses fixture EvidenceBundles. "
            "--gather fills missing D1 bundles through the Retrieval Wing gather API. "
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
            "Refused when the fixture is marked dry_run."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/retrieval/scifact_bm25.yaml"),
        help="Retrieval YAML. Used only with --gather.",
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
