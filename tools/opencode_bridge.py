#!/usr/bin/env python3
"""OpenAI-compatible bridge over an OpenCode session server.

Why this exists
---------------
The validators in this repository talk to an OpenAI-compatible chat endpoint.
Some model endpoints (notably the OpenCode-hosted free tier) are only reachable
through the OpenCode runtime, which has no OpenAI-compatible HTTP surface of
its own. This bridge exposes ``POST /v1/chat/completions`` on loopback and
maps each request onto **one fresh OpenCode session** that performs a single
stateless generation.

Design constraints that matter for the experiments
--------------------------------------------------
* **One session per call.** A session keeps its own message history. Reusing a
  session across claims would leak earlier claims into later ones, which would
  break the information-isolation guarantees the validator is measured on.
  Sessions are deleted after the call.
* **Loopback only.** The bridge binds ``127.0.0.1``. The repository's endpoint
  policy already allows loopback, so no policy change is required.
* **No silent repair.** A provider error, a tool call, or a missing assistant
  message is returned as HTTP 502 with the original message. The repository's
  client retries 502 and finally records a fail-closed execution status.
  A model response is never rewritten.
* **Usage is reported.** The assistant message token counters are returned in
  the OpenAI ``usage`` block so the repository's ``UsageMeter`` can record
  tokens and latency per run.

The harness prompt (agent system prompt plus tool definitions) is supplied by
OpenCode and is identical for every call, so it cancels out in comparisons
between conditions. It is included in the reported ``prompt_tokens``; see the
paper's cost section.

Usage
-----
Start an OpenCode server first::

    opencode serve --port 4097     # prints "server password <secret>"

Then start the bridge::

    OPENCODE_SERVER_PASSWORD=<secret> python3 tools/opencode_bridge.py --port 8801

and point a runner at it::

    PYTHONPATH=src python3 -m validator.same_evidence.runner \
        --config configs/baseline/same_evidence_b2.yaml \
        --live --base-url http://127.0.0.1:8801/v1 \
        --model-id opencode/minimax-m3.1-flash-free
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

DEFAULT_OPENCODE_BASE = "http://127.0.0.1:4097"
DEFAULT_MODEL = "opencode/minimax-m3.1-flash-free"
DEFAULT_AGENT = "build"
DEFAULT_LOCATION = "tools/opencode_agent"
POLL_SECONDS = 0.35
TEXT_PART_TYPES = frozenset({"text", "reasoning"})


class BridgeError(RuntimeError):
    """The OpenCode runtime could not produce one assistant message."""


class OpenCodeRuntime:
    """Thin client for the OpenCode session API."""

    def __init__(
        self,
        *,
        base_url: str,
        password: str,
        user: str = "opencode",
        agent: str = DEFAULT_AGENT,
        location: str = DEFAULT_LOCATION,
        timeout_seconds: float = 300.0,
        min_interval_seconds: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent = agent
        self.location = location
        self.timeout_seconds = timeout_seconds
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._auth = f"Basic {token}"
        self._lock = threading.Lock()
        self._counter = 0
        self._last_call = 0.0

    def _pace(self) -> None:
        """Keep a minimum interval between upstream generations.

        The hosted free tier throttles bursts and can refuse an account's
        requests outright. Pacing the bridge keeps the run inside the
        service's limit instead of losing claims to transport failures.
        """
        if self.min_interval_seconds <= 0:
            return
        with self._lock:
            wait = self._last_call + self.min_interval_seconds - time.time()
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.time()

    def _request(self, method: str, path: str, payload: dict | None = None, timeout: float = 120.0) -> Any:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", self._auth)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    def _next_title(self) -> str:
        with self._lock:
            self._counter += 1
            return f"mavs-bridge-{os.getpid()}-{self._counter}"

    @staticmethod
    def model_ref(model: str) -> dict:
        if "/" in model:
            provider, _, identifier = model.partition("/")
            return {"providerID": provider, "id": identifier}
        return {"providerID": "opencode", "id": model}

    def complete(self, model: str, system_prompt: str, user_prompt: str) -> dict:
        """Run one stateless generation and return text plus token usage."""
        self._pace()
        session = self._request(
            "POST",
            "/api/session",
            {
                "title": self._next_title(),
                "agent": self.agent,
                "model": self.model_ref(model),
                "location": {"directory": self.location},
            },
        )
        session_id = session["data"]["id"]
        try:
            prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
            self._request("POST", f"/api/session/{session_id}/prompt", {"text": prompt})
            assistant = self._await_assistant(session_id)
            error = assistant.get("error")
            if error:
                raise BridgeError(str(error.get("message", "provider error")))
            parts = assistant.get("content") or []
            texts = [part.get("text", "") for part in parts if part.get("type") == "text"]
            unexpected = sorted(
                {str(part.get("type")) for part in parts if part.get("type") not in TEXT_PART_TYPES}
            )
            if unexpected:
                raise BridgeError(f"model produced non-text output parts: {unexpected}")
            tokens = assistant.get("tokens") or {}
            prompt_tokens = int(tokens.get("input", 0))
            completion_tokens = int(tokens.get("output", 0))
            return {
                "text": "".join(texts),
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        finally:
            try:
                self._request("DELETE", f"/api/session/{session_id}", timeout=30.0)
            except Exception:  # noqa: BLE001 - cleanup is best effort
                pass

    def _await_assistant(self, session_id: str) -> dict:
        deadline = time.time() + self.timeout_seconds
        assistant: dict | None = None
        while time.time() < deadline:
            messages = self._request("GET", f"/api/session/{session_id}/message")
            for message in (messages or {}).get("data", []):
                if message.get("type") == "assistant":
                    assistant = message
            if assistant is not None and assistant.get("time", {}).get("completed"):
                return assistant
            time.sleep(POLL_SECONDS)
        raise BridgeError("no assistant message before the timeout")


class BridgeHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    runtime: OpenCodeRuntime
    default_model: str = DEFAULT_MODEL
    log_path: Path | None = None
    log_lock = threading.Lock()

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003 - http.server API
        return

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _log(self, record: dict) -> None:
        if self.log_path is None:
            return
        with self.log_lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        if self.path.rstrip("/") not in {"/v1/chat/completions", "/chat/completions"}:
            self._send(404, {"error": {"message": "unknown path"}})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": {"message": "request body is not JSON"}})
            return
        messages = body.get("messages") or []
        system_parts: list[str] = []
        user_parts: list[str] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, str):
                continue
            if message.get("role") == "system":
                system_parts.append(content)
            elif message.get("role") == "user":
                user_parts.append(content)
        model = body.get("model") or self.default_model
        started = time.perf_counter()
        try:
            result = self.runtime.complete(
                model, "\n".join(system_parts), "\n".join(user_parts)
            )
        except Exception as exc:  # noqa: BLE001 - reported to the caller as 502
            self._log(
                {
                    "model": model,
                    "status": "error",
                    "error": str(exc),
                    "latency_seconds": time.perf_counter() - started,
                }
            )
            self._send(502, {"error": {"type": "bridge_error", "message": str(exc)}})
            return
        latency = time.perf_counter() - started
        self._log(
            {
                "model": model,
                "status": "ok",
                "latency_seconds": latency,
                "usage": result["usage"],
            }
        )
        self._send(
            200,
            {
                "id": f"mavs-bridge-{int(started * 1000)}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": result["text"]},
                        "finish_reason": "stop",
                    }
                ],
                "usage": result["usage"],
            },
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8801)
    parser.add_argument("--opencode-base", default=os.environ.get("OPENCODE_BASE", DEFAULT_OPENCODE_BASE))
    parser.add_argument(
        "--password",
        default=os.environ.get("OPENCODE_SERVER_PASSWORD", ""),
        help="Server password printed by 'opencode serve'.",
    )
    parser.add_argument("--user", default=os.environ.get("OPENCODE_SERVER_USER", "opencode"))
    parser.add_argument("--agent", default=os.environ.get("OPENCODE_AGENT", DEFAULT_AGENT))
    parser.add_argument(
        "--location",
        default=os.environ.get("OPENCODE_LOCATION", DEFAULT_LOCATION),
        help="Directory whose opencode.json defines the agent.",
    )
    parser.add_argument("--model", default=os.environ.get("OPENCODE_MODEL", DEFAULT_MODEL))
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument(
        "--min-interval",
        type=float,
        default=float(os.environ.get("OPENCODE_MIN_INTERVAL", "0")),
        help=(
            "Minimum seconds between upstream generations. The hosted free "
            "tier throttles bursts, so a paced bridge keeps a long run inside "
            "the service's limit."
        ),
    )
    parser.add_argument("--log", default=None, help="Optional JSONL call log.")
    args = parser.parse_args(argv)
    if not args.password:
        print("bridge: a server password is required (--password or OPENCODE_SERVER_PASSWORD)")
        return 2
    if args.location and not Path(args.location).is_absolute():
        args.location = str(Path(__file__).resolve().parent.parent / args.location)
    BridgeHandler.runtime = OpenCodeRuntime(
        base_url=args.opencode_base,
        password=args.password,
        user=args.user,
        agent=args.agent,
        location=args.location,
        timeout_seconds=args.timeout_seconds,
        min_interval_seconds=args.min_interval,
    )
    BridgeHandler.default_model = args.model
    BridgeHandler.log_path = Path(args.log) if args.log else None
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    print(f"mavs bridge listening on http://{args.host}:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
