"""Drop failed-execution rows from a predictions file so a resume re-runs them.

An infrastructure failure (the endpoint refused the connection, the free
tier throttled the request) is recorded as a failed execution status rather
than a scientific label. Those rows are excluded from the scored metrics, but
a resumed run would skip them because their claim ids are already on disk.
This helper removes them so that the next attempt re-claims exactly those
claims. The previous file is kept as a ``.failed`` backup.

Usage:
    python3 scripts/paper/drop_failed_rows.py artifacts/minimax/dev300/b2/predictions.jsonl
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"{path} does not exist")
        return 2
    kept: list[dict] = []
    dropped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("execution_status") or "ok") != "ok":
            dropped += 1
            continue
        kept.append(row)
    if dropped == 0:
        print(f"{path}: no failed rows")
        return 0
    shutil.copyfile(path, path.with_suffix(path.suffix + ".failed"))
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
            for row in kept
        ),
        encoding="utf-8",
    )
    print(f"{path}: dropped {dropped} failed rows, {len(kept)} kept (backup: {path}.failed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
