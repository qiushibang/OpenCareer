"""Context-local SessionManager selection for multi-user cloud requests."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar, Token
from threading import Lock
from typing import Any, Callable

from .identity import Principal


class PrincipalManagerRegistry:
    def __init__(
        self,
        default_manager: Any,
        factory: Callable[[Principal], Any],
        *,
        max_managers: int = 50,
    ) -> None:
        self._default_manager = default_manager
        self._factory = factory
        self._max_managers = max_managers
        self._managers: dict[str, Any] = {}
        self._lock = Lock()
        self._current: ContextVar[Any | None] = ContextVar(
            "opencareer_principal_manager",
            default=None,
        )

    def activate(self, principal: Principal) -> Token:
        manager = self._managers.get(principal.user_id)
        if manager is None:
            with self._lock:
                manager = self._managers.get(principal.user_id)
                if manager is None:
                    if len(self._managers) >= self._max_managers:
                        raise RuntimeError(
                            "OpenCareer user manager capacity reached"
                        )
                    manager = self._factory(principal)
                    self._managers[principal.user_id] = manager
        return self._current.set(manager)

    def deactivate(self, token: Token) -> None:
        self._current.reset(token)

    def __getattr__(self, name: str):
        manager = self._current.get() or self._default_manager
        return getattr(manager, name)

    async def aclose(self) -> None:
        managers = [self._default_manager, *self._managers.values()]
        results = []
        seen: set[int] = set()
        for manager in managers:
            if id(manager) in seen:
                continue
            seen.add(id(manager))
            results.append(manager.aclose())
        if results:
            await asyncio.gather(*results)
