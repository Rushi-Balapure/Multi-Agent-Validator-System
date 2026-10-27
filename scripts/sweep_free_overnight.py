#!/usr/bin/env python3
"""Keep the free-model sweep moving across an unreliable free tier.

The hosted free tier answers for a while, then refuses every request for an
unknown cool-down period, then answers again. A single long run loses the
remainder of its claims to that window. This supervisor runs one model at a
time, probes before each attempt, and backs off geometrically while the tier
is refusing. Every condition is resumable, so progress is never lost.

Usage:
    .venv-mavs/bin/python scripts/sweep_free_overnight.py \
        --deadline-hours 12 --log /tmp/opencode/free_sweep.log

It never touches the closed-weight models; that half of the sweep is complete
and already paid for.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = "http://127.0.0.1:8801/v1"
OUT = ROOT / "artifacts" / "sweep"
MODELS = {
    "deepseek": "opencode/deepseek-v4.1-flash-free",
    "glm": "opencode/glm-5.3-flash-free",
    "flint": "opencode/flint-40b-free",
    "beam": "opencode/beam-free",
    "mimo": "opencode/mimo-v2.6-flash-free",
    "nemotron": "opencode/nemotron-3.5-super-vl-free",
    "pickle": "opencode/big-pickle",
}
N_CLAIMS = 30


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%H:%M:%SZ")
    print(f"[{stamp}] {message}", flush=True)


def complete(key: str) -> bool:
    for side in ("b2", "v"):
        path = OUT / key / side / "predictions.jsonl"
        if not path.is_file():
            return False
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        ok = [row for row in rows if str(row.get("execution_status") or "ok") == "ok"]
        if len(rows) < N_CLAIMS or len(ok) != len(rows):
            return False
    return True


def probe(model: str) -> tuple[bool, str]:
    """One tiny request. True when the tier is answering again."""
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        }
    ).encode()
    request = urllib.request.Request(
        f"{BRIDGE}/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            json.load(response)
        return True, ""
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:  # noqa: BLE001 - best effort
            pass
        detail = str(detail)[:120]
        # A finished generation that invoked a tool instead of replying
        # still proves the tier is processing requests.
        if "non-text output parts" in detail:
            return True, detail
        return False, detail
    except Exception as exc:  # noqa: BLE001 - transport problems are retryable
        return False, f"{type(exc).__name__}: {exc}"[:120]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deadline-hours", type=float, default=12.0)
    parser.add_argument("--min-wait", type=float, default=300.0)
    parser.add_argument("--max-wait", type=float, default=1800.0)
    parser.add_argument("--run-timeout", type=float, default=7200.0)
    args = parser.parse_args()

    deadline = time.time() + args.deadline_hours * 3600
    wait = args.min_wait
    while time.time() < deadline:
        pending = [key for key in MODELS if not complete(key)]
        if not pending:
            log("all free models complete")
            return 0
        # Probe every pending model: a dead per-model quota must not block
        # the models behind it, so take the first one that answers.
        log(f"probing {len(pending)} pending model(s): {', '.join(pending)}")
        ready: list[str] = []
        for key in pending:
            okay, detail = probe(MODELS[key])
            if okay:
                ready.append(key)
            else:
                log(f"  {key} refusing ({detail})")
        if not ready:
            log(f"all pending models refusing; sleeping {int(wait)}s")
            time.sleep(wait)
            wait = min(wait * 2, args.max_wait)
            continue

        wait = args.min_wait
        key = ready[0]
        model = MODELS[key]
        other = [k for k in pending if k != key]
        log(f"tier answering; running {key}" + (f"; waiting on {len(other)}" if other else ""))
        started = time.time()
        try:
            result = subprocess.run(
                ["bash", "scripts/run_model_sweep.sh", key],
                cwd=ROOT,
                timeout=args.run_timeout,
                capture_output=True,
                text=True,
            )
            tail = "\n".join(result.stdout.splitlines()[-6:])
            log(f"{key} exit={result.returncode} after {int(time.time() - started)}s\n{tail}")
        except subprocess.TimeoutExpired:
            log(f"{key} run timed out after {int(time.time() - started)}s; resuming later")
        except Exception as exc:  # noqa: BLE001 - keep the supervisor alive
            log(f"{key} run failed to start: {type(exc).__name__}: {exc}")
        if complete(key):
            log(f"{key} complete")
        else:
            # The window closed mid-run. Back off before the next attempt.
            time.sleep(wait)
            wait = min(wait * 2, args.max_wait)
    log("deadline reached; run the supervisor again to resume")
    return 1


if __name__ == "__main__":
    sys.exit(main())
