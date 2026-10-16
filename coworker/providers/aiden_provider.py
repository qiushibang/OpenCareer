"""Aiden Responses provider using the local login's short-lived JWT."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from typing import Any

from .openai_responses import OpenAIResponsesProvider

AIDEN_BASE_URL = "https://aiden-aiproxy.bytedance.net/v2"

_HEADER_ENV = {
    "X-Aiden-X-Client": "AIDEN_X_HEADER_X_AIDEN_X_CLIENT",
    "X-Aiden-Session-Id": "AIDEN_X_HEADER_X_AIDEN_SESSION_ID",
    "X-Aiden-Terminal-Id": "AIDEN_X_HEADER_X_AIDEN_TERMINAL_ID",
}


def aiden_headers(env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Read optional Aiden X headers from this process without persisting them."""
    values = env if env is not None else os.environ
    headers: dict[str, str] = {}
    for header, base_name in _HEADER_ENV.items():
        value = (values.get(base_name) or "").strip()
        if not value:
            for name in sorted(values):
                if name.startswith(base_name + "_"):
                    value = (values.get(name) or "").strip()
                    if value:
                        break
        if value:
            headers[header] = value
    return headers


def get_aiden_token(aiden_path: str | None = None) -> str:
    executable = (
        (aiden_path or "").strip()
        or os.environ.get("AIDEN_CLI_PATH", "").strip()
        or shutil.which("aiden")
    )
    if not executable:
        raise RuntimeError(
            "Aiden CLI was not found. Install Aiden or configure its executable path."
        )
    try:
        result = subprocess.run(
            [executable, "auth", "get-bytecloud-jwt-token"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            "Could not obtain an Aiden login token. Sign in with the Aiden CLI."
        ) from exc
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("Aiden CLI returned an empty login token.")
    return token


class AidenResponsesProvider(OpenAIResponsesProvider):
    """OpenAI Responses-compatible Aiden gateway with per-request token refresh."""

    def __init__(
        self,
        client: Any = None,
        *,
        aiden_path: str | None = None,
        token_provider: Callable[[], str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(client=client, default_model="deepseek-v4-flash")
        self._token_provider = token_provider or (lambda: get_aiden_token(aiden_path))
        self._env = env

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._token_provider,
                base_url=AIDEN_BASE_URL,
                default_headers=aiden_headers(self._env),
            )
        return self._client
