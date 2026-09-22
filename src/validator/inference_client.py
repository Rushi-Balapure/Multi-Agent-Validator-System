"""OpenAI-compatible chat for a loopback or RFC1918 host.

The allowlist is Baseline B2's ``assert_local_or_private`` (loopback or
RFC1918 only, including redirects). This module imports that policy. It does
not copy it and it does not change the baseline runner.

Default deployment, also recorded in ``configs/judgment/fixture_live.yaml``:

    base_url: http://127.0.0.1:1234/v1
    model_id: qwen2.5-coder-1.5b-instruct

``http://192.168.1.10:1234/v1`` and other RFC1918 hosts are allowed. Public
hostnames and non-private addresses are refused. No cloud API is called.
"""

from __future__ import annotations

from validator.same_evidence.b2 import (
    BaselineDataError,
    EndpointUnavailable,
    OpenAICompatibleClient,
    assert_local_or_private,
)

DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL_ID = "qwen2.5-coder-1.5b-instruct"


class EndpointPolicyError(RuntimeError):
    """``base_url`` is not loopback or an RFC1918 address."""


class InferenceTransportError(RuntimeError):
    """The local endpoint could not return a chat completion.

    ``timed_out`` is true only for a timeout. Other failures, including a
    redirect off the private network, are not timeouts.
    """

    def __init__(self, message: str, *, timed_out: bool) -> None:
        super().__init__(message)
        self.timed_out = timed_out


class LocalChatClient:
    """Chat completions against the baseline local-or-private client.

    Construction refuses a public ``base_url`` before any socket is opened.
    The POST and the redirect guard are Baseline's ``OpenAICompatibleClient``.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        temperature: float,
        timeout_seconds: float,
    ) -> None:
        try:
            assert_local_or_private(base_url)
        except BaselineDataError as exc:
            raise EndpointPolicyError(str(exc)) from exc
        self.base_url = base_url
        self.model_id = model_id
        self._client = OpenAICompatibleClient(
            base_url=base_url,
            model_id=model_id,
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )

    def complete(self, system_prompt: str, payload: dict) -> str:
        """Return the assistant message text. The payload is sent unchanged."""
        try:
            return self._client._chat(system_prompt, payload)
        except EndpointUnavailable as exc:
            raise InferenceTransportError(
                str(exc),
                timed_out=isinstance(exc.__cause__, TimeoutError),
            ) from exc
        except BaselineDataError as exc:
            raise InferenceTransportError(str(exc), timed_out=False) from exc
