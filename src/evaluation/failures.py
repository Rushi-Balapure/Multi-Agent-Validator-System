"""V failure / reason-code breakdown, including descriptive RQ2 splits."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


def breakdown(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    status = Counter(str(row.get("execution_status") or "ok") for row in rows)
    four = Counter(str(row.get("label_4way") or "") for row in rows)
    native = Counter(str(row.get("label") or "") for row in rows)
    codes: Counter[str] = Counter()
    for row in rows:
        for code in row.get("rationale_codes") or []:
            codes[str(code)] += 1
    nei = [row for row in rows if row.get("label") == "NEI"]
    rq2 = Counter(str(row.get("label_4way") or "") for row in nei)
    return {
        "n": len(rows),
        "execution_status": dict(status),
        "label": dict(native),
        "label_4way": dict(four),
        "rationale_codes": dict(codes),
        "rq2_descriptive": {
            "n_predicted_nei": len(nei),
            "unaddressed": rq2.get("unaddressed", 0),
            "underdetermined": rq2.get("underdetermined", 0),
            "note": "SciFact NEI gold cannot score this four-way split.",
        },
    }
