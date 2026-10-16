from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app
from coworker.server import run as server_run
from coworker.server.identity import Principal
from coworker.server.principal_managers import PrincipalManagerRegistry
from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.runtime.redis_coordinator import RedisRuntimeCoordinator
from coworker.storage.factory import build_storage_runtime
from coworker.storage.postgres.conversations import (
    PostgresConversationRepository,
)


class _Database:
    def __init__(self) -> None:
        self.checked = False
        self.migrated = False
        self.closed = False

    def check(self) -> None:
        self.checked = True

    def migrate(self) -> tuple[int, ...]:
        self.migrated = True
        return (1,)

    def close(self) -> None:
        self.closed = True


class _Redis:
    def __init__(self) -> None:
        self.pinged = False
        self.closed = False

    def ping(self) -> bool:
        self.pinged = True
        return True

    def close(self) -> None:
        self.closed = True


def test_storage_factory_keeps_desktop_local_without_cloud_urls() -> None:
    runtime = build_storage_runtime(environ={})

    assert runtime.mode == "local"
    assert runtime.origin_repository is None
    assert isinstance(runtime.coordinator, LocalRuntimeCoordinator)
    assert runtime.health() == {
        "mode": "local",
        "postgres": "not_configured",
        "redis": "not_configured",
    }


def test_storage_factory_initializes_both_cloud_services() -> None:
    database = _Database()
    redis = _Redis()

    runtime = build_storage_runtime(
        environ={
            "DATABASE_URL": "postgresql://secret@postgres/opencareer",
            "REDIS_URL": "redis://redis:6379/0",
        },
        database_factory=lambda _url: database,
        redis_factory=lambda _url: redis,
    )

    assert runtime.mode == "postgres"
    assert database.checked
    assert database.migrated
    assert redis.pinged
    assert runtime.origin_repository is not None
    assert isinstance(runtime.coordinator, RedisRuntimeCoordinator)
    assert runtime.health() == {
        "mode": "postgres",
        "postgres": "ready",
        "redis": "ready",
    }

    runtime.close()
    assert database.closed
    assert redis.closed


def test_storage_factory_requires_postgres_and_redis_together() -> None:
    with pytest.raises(RuntimeError, match="configured together"):
        build_storage_runtime(
            environ={"DATABASE_URL": "postgresql://postgres/opencareer"}
        )


def test_storage_factory_hides_credentials_when_cloud_is_unavailable() -> None:
    database_url = "postgresql://opencareer:do-not-print@postgres/opencareer"

    def unavailable(_url: str) -> _Database:
        raise OSError(database_url)

    with pytest.raises(RuntimeError) as error:
        build_storage_runtime(
            environ={
                "DATABASE_URL": database_url,
                "REDIS_URL": "redis://redis:6379/0",
            },
            database_factory=unavailable,
            redis_factory=lambda _url: _Redis(),
        )

    assert str(error.value) == "cloud storage initialization failed"
    assert "do-not-print" not in str(error.value)


def test_app_uses_cloud_storage_for_origin_health_and_shutdown(
    tmp_path,
) -> None:
    class Origins:
        def enabled_origins(self) -> tuple[str, ...]:
            return ("https://alpha.example.com",)

    class Runtime:
        origin_repository = Origins()
        closed = False

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            self.closed = True

    runtime = Runtime()
    from extensions.support.diagnostics import DiagnosticStore
    app = create_app(
        SessionManager(data_dir=tmp_path / "state"),
        storage_runtime=runtime,
        diagnostic_store=DiagnosticStore(path=tmp_path / "support.db"),
    )

    with TestClient(app) as client:
        health = client.get("/v1/health").json()
        response = client.get(
            "/v1/sessions",
            headers={"Origin": "https://alpha.example.com"},
        )

        assert health["storage"] == runtime.health()
        assert (
            response.headers.get("access-control-allow-origin")
            == "https://alpha.example.com"
        )

    assert runtime.closed


def test_server_build_app_selects_storage_runtime(
    tmp_path,
    monkeypatch,
) -> None:
    class Runtime:
        mode = "local"
        database = None
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def health(self) -> dict[str, str]:
            return {
                "mode": "local",
                "postgres": "not_configured",
                "redis": "not_configured",
            }

        def close(self) -> None:
            pass

    runtime = Runtime()
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        server_run,
        "build_storage_runtime",
        lambda: runtime,
    )

    app = server_run.build_app(None, "test:model", "interactive")

    assert app.state.storage_runtime is runtime


def test_server_build_app_uses_principal_managers_in_cloud(
    tmp_path,
    monkeypatch,
) -> None:
    class Runtime:
        mode = "postgres"
        database = object()
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            pass

    runtime = Runtime()
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(
        server_run,
        "build_storage_runtime",
        lambda: runtime,
    )

    app = server_run.build_app(None, "test:model", "interactive")

    assert isinstance(app.state.manager, PrincipalManagerRegistry)
    token = app.state.manager.activate(Principal("alice", "test"))
    try:
        assert isinstance(
            app.state.manager.session_store,
            PostgresConversationRepository,
        )
        assert app.state.manager.runtime_coordinator is runtime.coordinator
        assert app.state.manager.career_mcp_principal_user_id == "alice"
    finally:
        app.state.manager.deactivate(token)


def test_server_build_app_wires_hosted_auth_only_to_postgres(
    tmp_path,
    monkeypatch,
) -> None:
    class Runtime:
        mode = "postgres"
        database = object()
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def health(self) -> dict[str, str]:
            return {}

        def close(self) -> None:
            pass

    class Provider:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    runtime = Runtime()
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("OPENCAR_AUTH_ISSUER", "https://tenant.authing.cn/oidc")
    monkeypatch.setenv("OPENCAR_AUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("OPENCAR_AUTH_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv(
        "OPENCAR_AUTH_REDIRECT_URI",
        "https://app.opencareer.online/_openworker/auth/callback",
    )
    monkeypatch.setenv(
        "OPENCAR_AUTH_STATE_SECRET",
        "state-secret-with-at-least-32-characters",
    )
    monkeypatch.setattr(server_run, "build_storage_runtime", lambda: runtime)
    monkeypatch.setattr(server_run, "AuthingIdentityProvider", Provider)

    app = server_run.build_app(None, "test:model", "interactive")

    assert app.state.auth_module is not None
    assert app.state.auth_module.settings.client_id == "client-id"
