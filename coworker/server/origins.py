"""Exact browser Origin validation shared by HTTP and WebSocket routes."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Protocol
from urllib.parse import urlsplit

logger = logging.getLogger("coworker.server.origins")

DEFAULT_ORIGINS = (
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:1420",
    "http://127.0.0.1:1420",
)


class OriginRepository(Protocol):
    def enabled_origins(self) -> tuple[str, ...]: ...


def normalize_origin(raw: str) -> str:
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https", "tauri"} or not parsed.hostname:
        raise ValueError("origin must use http, https, or tauri and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("origin must not include credentials")
    if parsed.path or parsed.query or parsed.fragment:
        raise ValueError("origin must not include path, query, or fragment")
    host = parsed.hostname
    if "*" in host:
        raise ValueError("origin must not contain a wildcard")
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("origin host or port is invalid") from exc
    if parsed.scheme == "tauri" and port is not None:
        raise ValueError("tauri origin must not include a port")
    default_port = 443 if parsed.scheme == "https" else 80
    suffix = (
        ""
        if parsed.scheme == "tauri" or port is None or port == default_port
        else f":{port}"
    )
    if ":" in ascii_host:
        ascii_host = f"[{ascii_host}]"
    return f"{parsed.scheme}://{ascii_host}{suffix}"


class OriginPolicy:
    def __init__(self, origins: Iterable[str]) -> None:
        self._origins = frozenset(normalize_origin(origin) for origin in origins)

    @property
    def origins(self) -> tuple[str, ...]:
        return tuple(sorted(self._origins))

    def allows(self, origin: str | None) -> bool:
        if not origin:
            return False
        try:
            normalized = normalize_origin(origin)
        except ValueError:
            return False
        return normalized in self._origins


def build_origin_policy(
    *,
    defaults: Iterable[str] = DEFAULT_ORIGINS,
    emergency_origins: str = "",
    repository: OriginRepository | None = None,
) -> OriginPolicy:
    origins = list(defaults)
    origins.extend(
        origin.strip()
        for origin in emergency_origins.split(",")
        if origin.strip()
    )
    if repository is not None:
        try:
            origins.extend(repository.enabled_origins())
        except Exception:
            logger.exception(
                "Could not load deployment origins; database origins are disabled"
            )
    return OriginPolicy(origins)
