"""Extract readable case studies from the scored development rows.

The paper's acceptance checklist asks for at least one unsupported-synthesis
case and one validator failure next to the successes. This script selects
them deterministically from the saved predictions:

* ``missed_support``    gold SUPPORT, V abstained, the two scopes agreed
                        (a genuine loss of coverage);
* ``scope_conflict``    gold SUPPORT, V abstained, the two scopes disagreed
                        (the conservative mode);
* ``citation_defect``   the citation auditor marked a citation inadequate and
                        V abstained although the baseline endorsed the claim;
* ``false_endorsement`` the baseline endorsed a claim the gold does not
                        support (a validator failure).

Every selected case prints the claim, the gold label, both methods' labels,
the two scope labels, and the rationale that the run recorded.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from data.scifact_loader import load_split  # noqa: E402
from evaluation.score_predictions import score_predictions_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
REGISTRY = TABLES / "run_registry.json"


def _native_gold(label: str) -> str:
    token = str(label).strip().upper()
    return "REFUTE" if token == "CONTRADICT" else token


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


_LATEX_ESCAPES = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "\\": r"\textbackslash{}",
}


def _tex(text: str) -> str:
    """Escape a string for LaTeX. The claim text comes from the corpus."""
    out = []
    for character in str(text):
        out.append(_LATEX_ESCAPES.get(character, character))
    return "".join(out)


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    family = "gpt-6-luna"
    conditions = registry["families"][family]["dev300"]
    split = registry["splits"]["dev300"]

    b2_dir = ROOT / conditions["B2"]
    v_dir = ROOT / conditions["V"]
    b2_report = score_predictions_file(
        b2_dir / "predictions.jsonl", run_sidecar=b2_dir / "run.json", join_gold=split
    )
    gold_by_id = {
        item["claim_id"]: _native_gold(item["label_gold"])
        for item in (b2_report.get("gold_join") or {}).get("claims") or []
        if item.get("label_gold")
    }
    claims = {
        bundle.claim.claim_id: bundle.claim.normalized_claim
        for bundle in load_split(split)
    }
    b2_rows = {row["claim_id"]: row for row in _read_jsonl(b2_dir / "predictions.jsonl")}
    v_rows = {row["claim_id"]: row for row in _read_jsonl(v_dir / "predictions.jsonl")}

    cases: dict[str, dict] = {}
    for claim_id in sorted(gold_by_id):
        gold = gold_by_id[claim_id]
        b2 = b2_rows.get(claim_id)
        v = v_rows.get(claim_id)
        if not b2 or not v:
            continue
        b2_label = str(b2.get("label"))
        v_label = str(v.get("label"))
        codes = list(v.get("rationale_codes") or [])
        if (
            "missed_support" not in cases
            and gold == "SUPPORT"
            and v_label == "NEI"
            and "labels_agree" in codes
            and b2_label == "SUPPORT"
        ):
            cases["missed_support"] = {"claim_id": claim_id, "gold": gold, "b2": b2_label, "v": v_label, "codes": codes}
        if (
            "scope_conflict" not in cases
            and gold == "SUPPORT"
            and v_label == "NEI"
            and "d0_d1_conflict" in codes
        ):
            cases["scope_conflict"] = {"claim_id": claim_id, "gold": gold, "b2": b2_label, "v": v_label, "codes": codes}
        if (
            "citation_defect" not in cases
            and gold == "SUPPORT"
            and v_label == "NEI"
            and "d0_not_repaired_from_d1" in codes
        ):
            cases["citation_defect"] = {"claim_id": claim_id, "gold": gold, "b2": b2_label, "v": v_label, "codes": codes}
        if (
            "false_endorsement" not in cases
            and gold in {"REFUTE", "NEI"}
            and b2_label == "SUPPORT"
        ):
            cases["false_endorsement"] = {"claim_id": claim_id, "gold": gold, "b2": b2_label, "v": v_label, "codes": codes}

    payload = []
    for name, case in cases.items():
        row_v = v_rows[case["claim_id"]]
        row_b2 = b2_rows[case["claim_id"]]
        payload.append(
            {
                "case": name,
                "claim_id": case["claim_id"],
                "claim": claims.get(case["claim_id"], ""),
                "gold": case["gold"],
                "b2_label": case["b2"],
                "b2_rationale": str(row_b2.get("rationale") or "")[:400],
                "v_label": case["v"],
                "v_label_4way": row_v.get("label_4way"),
                "d0_label_4way": row_v.get("d0_label_4way"),
                "d1_label_4way": row_v.get("d1_label_4way"),
                "v_rationale_codes": case["codes"],
            }
        )
    out = TABLES / "case_studies.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    titles = {
        "missed_support": "Coverage loss, scopes agree",
        "scope_conflict": "Scope conflict, abstained",
        "citation_defect": "Failed citation audit, abstained",
        "false_endorsement": "Baseline false endorsement",
    }
    readings = {
        "missed_support": "Both scopes call the evidence inconclusive; the validator abstains on a claim the baseline and the gold endorse.",
        "scope_conflict": "The independent scope finds support the citation scope does not; the reconciler refuses to choose and abstains.",
        "citation_defect": "The auditor judged the original citation inadequate; the validator declined to endorse from it.",
        "false_endorsement": "The baseline endorses from the original citations; the validator abstains, so the endorsement is caught but not replaced.",
    }
    lines = [
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}>{\\raggedright\\arraybackslash}p{0.20\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.09\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.09\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.165\\textwidth}"
        ">{\\raggedright\\arraybackslash}p{0.325\\textwidth}@{}}",
        "\\toprule",
        "Case and claim & Gold & B2 & V (D0 / D1) & What the record shows \\\\",
        "\\midrule",
    ]
    for entry in payload:
        scopes = f"{entry['d0_label_4way']} / {entry['d1_label_4way']}"
        lines.append(
            " & ".join(
                [
                    "\\textbf{" + _tex(titles.get(entry["case"], entry["case"])) + "}\n\\newline\n\\emph{" + _tex(entry["claim"]) + "}",
                    _tex(entry["gold"]),
                    _tex(entry["b2_label"]),
                    _tex(f"{entry['v_label']} ({scopes})"),
                    _tex(readings.get(entry["case"], "")),
                ]
            )
            + " \\\\[2pt]"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    PAPER_TABLES.mkdir(parents=True, exist_ok=True)
    (PAPER_TABLES / "t8_cases.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} with {len(payload)} cases")
    for entry in payload:
        print(f"  {entry['case']}: {entry['claim_id']} gold={entry['gold']} b2={entry['b2_label']} v={entry['v_label']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
