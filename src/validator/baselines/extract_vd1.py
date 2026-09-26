"""Extract the V-D1 ablation cell from a V predictions file.

V already stores ``d1_label_4way``. This is a mapping step, not a new model
run. Fail-closed V rows stay fail-closed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from validator.validator_v.labels import map_four_way_label


def vd1_row(row: Mapping[str, Any]) -> dict[str, Any]:
    four = row.get("d1_label_4way")
    if not isinstance(four, str) or not four:
        raise ValueError(f"{row.get('claim_id')} is missing d1_label_4way")
    native = map_four_way_label(four)
    copied = {
        "claim_id": row["claim_id"],
        "label": native,
        "label_4way": four,
        "adaptation": "V-D1",
        "method_id": "V-D1",
        "system_id": "validator_v",
        "inference_mode": row.get("inference_mode"),
        "execution_status": row.get("execution_status", "ok"),
        "source_method_id": "V",
    }
    if "label_gold" in row:
        copied["label_gold"] = row["label_gold"]
    return copied


def extract_vd1_file(predictions: Path, output: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in predictions.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(vd1_row(json.loads(line)))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return rows
