from __future__ import annotations

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from coworker.server import SessionManager, create_app
from coworker.server.auth import (
    AuthModule,
    AuthSession,
    AuthSettings,
    CompletedIdentity,
    IdentityClaims,
)
from coworker.server.identity import (
    LOCAL_USER,
    Principal,
    authentication_required,
    resolve_principal,
)
from coworker.server.principal_managers import PrincipalManagerRegistry


class _FakeIdentityProvider:
    def __init__(self) -> None:
        self.return_to = "/"
        self.force_login = False

    async def begin(
        self,
        request,
        *,
        redirect_uri: str,
        return_to: str,
        force_login: bool = False,
    ):
        from fastapi.responses import RedirectResponse

        self.return_to = return_to
        self.force_login = force_login
        return RedirectResponse("https://tenant.authing.cn/oidc/auth")

    async def complete(self, request) -> CompletedIdentity:
        return CompletedIdentity(
            claims=IdentityClaims(
                issuer="https://tenant.authing.cn/oidc",
                subject="authing-user-1",
                email="alice@example.com",
                email_verified=True,
                display_name="Alice",
            ),
            return_to=self.return_to,
        )


class _FakeAuthSessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, AuthSession] = {}

    def issue(self, claims: IdentityClaims, *, ttl_seconds: int):
        from coworker.server.auth import IssuedAuthSession

        session = AuthSession(
            principal=Principal("user-alice", "oidc-session"),
            email=claims.email,
            display_name=claims.display_name,
        )
        self.sessions["browser-session"] = session
        return IssuedAuthSession("browser-session", session)

    def resolve(self, raw_token: str | None) -> AuthSession | None:
        return self.sessions.get(raw_token or "")

    def revoke(self, raw_token: str | None) -> None:
        if raw_token:
            self.sessions.pop(raw_token, None)


class _RejectedIdentityProvider(_FakeIdentityProvider):
    async def complete(self, request) -> CompletedIdentity:
        raise RuntimeError("authorization-code-must-not-leak")


def test_hosted_auth_never_falls_back_to_shared_legacy_token(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_API_TOKEN", "diagnostic-legacy-token")
    auth = AuthModule(
        _FakeIdentityProvider(), _FakeAuthSessionStore(),
        AuthSettings(
            issuer="https://tenant.authing.cn/oidc", client_id="test", client_secret="test",
            redirect_uri="https://app.opencareer.online/_openworker/auth/callback",
            state_secret="state-secret-with-at-least-32-characters", cookie_secure=False,
        ),
    )
    client = TestClient(create_app(SessionManager(data_dir=tmp_path), auth_module=auth))
    assert client.get("/v1/agents", headers={"X-OpenWorker-Token": "diagnostic-legacy-token"}).status_code == 401
    assert client.get("/v1/auth/session", headers={"X-OpenWorker-Token": "diagnostic-legacy-token"}).json()["authenticated"] is False
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/events", subprotocols=["openworker", "diagnostic-legacy-token"]):
            pass


class _RepeatCallbackIdentityProvider(_FakeIdentityProvider):
    def __init__(self) -> None:
        super().__init__()
        self._callbacks = 0

    async def complete(self, request) -> CompletedIdentity:
        self._callbacks += 1
        if self._callbacks > 1:
            raise RuntimeError("authorization-code-was-already-used")
        return await super().complete(request)


def test_identity_defaults_to_local_without_auth(monkeypatch):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)

    assert resolve_principal(None, legacy_token="") == Principal(
        LOCAL_USER,
        "local",
    )
    assert authentication_required(legacy_token="") is False


def test_hosted_login_issues_and_revokes_an_http_only_session(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)
    monkeypatch.delenv("COWORKER_API_TOKEN", raising=False)
    provider = _FakeIdentityProvider()
    auth = AuthModule(
        provider,
        _FakeAuthSessionStore(),
        AuthSettings(
            issuer="https://tenant.authing.cn/oidc",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://app.opencareer.online/_openworker/auth/callback",
            state_secret="state-secret-with-at-least-32-characters",
            cookie_secure=False,
            session_ttl_seconds=3600,
        ),
    )
    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            auth_module=auth,
        )
    )

    anonymous = client.get("/v1/auth/session")
    assert anonymous.json() == {
        "configured": True,
        "authenticated": False,
        "user": None,
    }
    login = client.get(
        "/auth/login",
        params={"return_to": "/career/jobs"},
        follow_redirects=False,
    )
    assert login.status_code == 307
    assert login.headers["location"].startswith("https://tenant.authing.cn/")

    callback = client.get("/auth/callback", follow_redirects=False)
    assert callback.status_code == 307
    assert callback.headers["location"] == "/career/jobs"
    assert "opencar_session=" in callback.headers["set-cookie"]
    assert "HttpOnly" in callback.headers["set-cookie"]
    assert "SameSite=lax" in callback.headers["set-cookie"]

    signed_in = client.get("/v1/auth/session")
    assert signed_in.json() == {
        "configured": True,
        "authenticated": True,
        "user": {
            "id": "user-alice",
            "email": "alice@example.com",
            "display_name": "Alice",
        },
    }
    assert client.get("/v1/agents").status_code == 200
    with client.websocket_connect(
        "/ws/events",
        subprotocols=["openworker"],
    ) as websocket:
        assert websocket.accepted_subprotocol == "openworker"

    logout = client.post("/auth/logout")
    assert logout.status_code == 200
    assert logout.json() == {"ok": True}
    assert client.get("/v1/auth/session").json()["authenticated"] is False

    forced_login = client.get(
        "/auth/login",
        params={"return_to": "/", "prompt": "login"},
        follow_redirects=False,
    )
    assert forced_login.status_code == 307
    assert provider.force_login is True


def test_identity_accepts_the_launch_legacy_token(monkeypatch):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)

    assert resolve_principal(
        "legacy",
        legacy_token="legacy",
    ) == Principal(LOCAL_USER, "legacy-token")
    assert resolve_principal("wrong", legacy_token="legacy") is None
    assert authentication_required(legacy_token="legacy") is True


def test_hosted_callback_recovers_to_the_login_screen_without_leaking_details(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)
    monkeypatch.delenv("COWORKER_API_TOKEN", raising=False)
    auth = AuthModule(
        _RejectedIdentityProvider(),
        _FakeAuthSessionStore(),
        AuthSettings(
            issuer="https://tenant.authing.cn/oidc",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://app.opencareer.online/_openworker/auth/callback",
            state_secret="state-secret-with-at-least-32-characters",
            cookie_secure=False,
        ),
    )
    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            auth_module=auth,
        ),
        raise_server_exceptions=False,
    )

    response = client.get("/auth/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/?auth_error=login_failed"
    assert "authorization-code" not in response.headers["location"]


def test_repeated_callback_returns_home_for_an_already_signed_in_browser(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)
    monkeypatch.delenv("COWORKER_API_TOKEN", raising=False)
    auth = AuthModule(
        _RepeatCallbackIdentityProvider(),
        _FakeAuthSessionStore(),
        AuthSettings(
            issuer="https://tenant.authing.cn/oidc",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://app.opencareer.online/_openworker/auth/callback",
            state_secret="state-secret-with-at-least-32-characters",
            cookie_secure=False,
        ),
    )
    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            auth_module=auth,
        ),
        raise_server_exceptions=False,
    )

    first = client.get("/auth/callback", follow_redirects=False)
    repeated = client.get("/auth/callback", follow_redirects=False)

    assert first.status_code == 307
    assert repeated.status_code == 307
    assert repeated.headers["location"] == "/"


def test_user_token_table_disables_legacy_token(monkeypatch):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice:tok-a,bob:tok-b",
    )

    assert resolve_principal(
        "tok-a",
        legacy_token="legacy",
    ) == Principal("alice", "user-token")
    assert resolve_principal(
        "tok-b",
        legacy_token="legacy",
    ) == Principal("bob", "user-token")
    assert resolve_principal("legacy", legacy_token="legacy") is None
    assert authentication_required(legacy_token="legacy") is True


def test_malformed_user_token_config_fails_closed(monkeypatch):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "missing-separator,alice:, :token",
    )

    assert resolve_principal("legacy", legacy_token="legacy") is None
    assert resolve_principal(None, legacy_token="") is None
    assert authentication_required(legacy_token="") is True


def test_duplicate_token_for_different_users_fails_closed(monkeypatch):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice:shared,bob:shared",
    )

    assert resolve_principal("shared", legacy_token="") is None


def test_http_auth_attaches_distinct_principals(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice:tok-a,bob:tok-b",
    )
    monkeypatch.setenv("COWORKER_API_TOKEN", "legacy")
    app = create_app(SessionManager(data_dir=tmp_path / "state"))

    @app.get("/_test/principal")
    def principal(request: Request) -> dict[str, str]:
        return {
            "user_id": request.state.principal.user_id,
            "via": request.state.principal.via,
        }

    client = TestClient(app)
    assert client.get("/v1/health").json() == {"status": "ok"}
    assert client.get(
        "/_test/principal",
        headers={"X-OpenWorker-Token": "tok-a"},
    ).json() == {"user_id": "alice", "via": "user-token"}
    assert client.get(
        "/_test/principal",
        headers={"X-OpenWorker-Token": "tok-b"},
    ).json() == {"user_id": "bob", "via": "user-token"}
    assert client.get(
        "/_test/principal",
        headers={"X-OpenWorker-Token": "legacy"},
    ).status_code == 401
    assert client.get(
        "/v1/health",
        headers={"X-OpenWorker-Token": "tok-a"},
    ).json()["default_workspace"] is None


def test_websocket_accepts_each_user_token_and_rejects_legacy(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice:tok-a,bob:tok-b",
    )
    monkeypatch.setenv("COWORKER_API_TOKEN", "legacy")
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state"))
    )

    for token in ("tok-a", "tok-b"):
        with client.websocket_connect(
            "/ws/events",
            subprotocols=["openworker", token],
        ) as websocket:
            assert websocket.accepted_subprotocol == "openworker"

    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            "/ws/events",
            subprotocols=["openworker", "legacy"],
        ) as websocket:
            websocket.receive_text()
    assert denied.value.code == 1008


def test_http_request_uses_the_principal_manager(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice:tok-a,bob:tok-b",
    )
    base = SessionManager(data_dir=tmp_path / "base")
    base.tenant_marker = "default"

    def manager_for(principal: Principal) -> SessionManager:
        manager = SessionManager(
            data_dir=tmp_path / principal.user_id,
        )
        manager.tenant_marker = principal.user_id
        return manager

    registry = PrincipalManagerRegistry(base, manager_for)
    app = create_app(registry)

    @app.get("/_test/manager")
    def current_manager() -> dict[str, str]:
        return {"user_id": app.state.manager.tenant_marker}

    client = TestClient(app)
    assert client.get(
        "/_test/manager",
        headers={"X-OpenWorker-Token": "tok-a"},
    ).json() == {"user_id": "alice"}
    assert client.get(
        "/_test/manager",
        headers={"X-OpenWorker-Token": "tok-b"},
    ).json() == {"user_id": "bob"}


def test_websocket_echoes_openworker_subprotocol_without_auth(
    tmp_path, monkeypatch
):
    """A tokenless local backend must still answer the proxied browser handshake.

    The alpha/hosted GUI always offers ["openworker"] and a browser aborts a
    handshake that selects none of the offered subprotocols — before this fix a
    local dev backend (no auth module, no token env) accepted then broke that
    mode, so turns silently never reached the backend.
    """
    monkeypatch.delenv("COWORKER_API_TOKEN", raising=False)
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)

    app = create_app(SessionManager(data_dir=tmp_path / "state"))
    client = TestClient(app)

    with client.websocket_connect(
        "/ws/events", subprotocols=["openworker"]
    ) as websocket:
        assert websocket.accepted_subprotocol == "openworker"
