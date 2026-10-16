# OpenCareer M1 Multi-Tenant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the M0 one-container-per-user Alpha into one process serving multiple isolated users without changing desktop single-user behavior or weakening Alpha security.

**Architecture:** Introduce request identity first, then derive per-user Career paths, then add a bounded per-user `SessionManager` registry, and only then consolidate deployment. Static tokens are an M1a transport detail; all callers consume a `Principal` so M1b can replace token parsing with verified JWT claims without changing storage routing.

**Tech Stack:** Python 3.12, FastAPI/Starlette, WebSocket subprotocol authentication, SQLite, pytest, Docker Compose, Caddy.

---

## Non-Negotiable Gates

- M0 server Docker build and browser/WebSocket smoke must pass before M1a deployment.
- `OPENCAR_EXTRA_ORIGINS` remains exact-match; no wildcard fallback.
- Alpha frontend remains token-free and is built only with `deploy/build-frontend.sh`.
- Desktop without multi-user configuration remains `Principal("local", "local")`.
- If `OPENCAR_USER_TOKENS` is configured, the legacy token is rejected.
- No user-derived path is created before the user ID passes `[A-Za-z0-9_-]{1,64}`.
- Career database, private resumes, OpenWorker state, workspace and MCP subprocess environment must all resolve to the same user.
- M1a-1 through M1a-4 are separate commits and deployment gates.

## File Map

### M1a-1 Request Identity

- Create `coworker/server/identity.py`: immutable `Principal`, static-token parsing and legacy/local fallback.
- Create `tests/test_server_identity.py`: pure identity and HTTP/WS integration tests.
- Modify `coworker/server/app.py`: attach principals to authenticated HTTP and WebSocket scopes.
- Modify `tests/test_server.py`: keep existing sidecar-token contract covered.

### M1a-2 Per-User Career Data

- Modify `extensions/career_mcp/config.py`: explicit private directory and validated `for_user`.
- Modify Career services under `extensions/career_mcp/services/`: accept injected `CareerConfig`.
- Modify `coworker/server/app.py`: build Career services from the request principal.
- Create `tests/test_career_tenant_isolation.py`: cross-token database and private-file isolation.

### M1a-3 Per-User OpenWorker Runtime

- Create `coworker/server/managers.py`: bounded, lazy `ManagerRegistry`.
- Modify `coworker/server/run.py`: choose one manager for desktop or a registry for multi-user mode.
- Modify `coworker/server/app.py`: resolve manager from HTTP/WS principal.
- Modify `coworker/server/manager.py` and MCP configuration wiring: pass user-specific state, Career and private directories to MCP subprocesses.
- Create `tests/test_manager_registry.py`: creation, reuse, eviction and close behavior.
- Create `tests/test_mcp_tenant_environment.py`: assert per-user subprocess environment.

### M1a-4 Deployment Consolidation

- Create `deploy/docker-compose.multi.yml`: one backend, one shared volume and static token map.
- Modify `deploy/Caddyfile`: all user subdomains proxy to the same backend while injecting distinct tokens.
- Modify `deploy/.env.example`: multi-user token-map example without secrets.
- Modify `deploy/README.md`: migration, rollback and acceptance commands.

## Task 1: M1a-1 Pure Identity Contract

**Files:**
- Create: `coworker/server/identity.py`
- Create: `tests/test_server_identity.py`

- [x] **Step 1: Write the failing pure identity tests**

```python
from coworker.server.identity import LOCAL_USER, Principal, resolve_principal


def test_identity_defaults_to_local_without_auth(monkeypatch):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)
    assert resolve_principal(None, legacy_token="") == Principal(LOCAL_USER, "local")


def test_identity_accepts_the_launch_legacy_token(monkeypatch):
    monkeypatch.delenv("OPENCAR_USER_TOKENS", raising=False)
    assert resolve_principal("legacy", legacy_token="legacy") == Principal(
        LOCAL_USER, "legacy-token"
    )
    assert resolve_principal("wrong", legacy_token="legacy") is None


def test_user_token_table_disables_legacy_token(monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:tok-a,bob:tok-b")
    assert resolve_principal("tok-a", legacy_token="legacy") == Principal(
        "alice", "user-token"
    )
    assert resolve_principal("tok-b", legacy_token="legacy") == Principal(
        "bob", "user-token"
    )
    assert resolve_principal("legacy", legacy_token="legacy") is None
```

- [x] **Step 2: Run RED**

Run:

```bash
.venv/bin/pytest -q tests/test_server_identity.py
```

Expected: collection fails because `coworker.server.identity` does not exist.

- [x] **Step 3: Implement the minimal identity module**

```python
"""Resolve transport credentials into an authenticated OpenCareer principal."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

LOCAL_USER = "local"
USER_TOKENS_ENV = "OPENCAR_USER_TOKENS"


@dataclass(frozen=True)
class Principal:
    user_id: str
    via: str


def _user_tokens() -> tuple[tuple[str, str], ...]:
    pairs: list[tuple[str, str]] = []
    for raw in os.environ.get(USER_TOKENS_ENV, "").split(","):
        user_id, separator, token = raw.strip().partition(":")
        if separator and user_id.strip() and token.strip():
            pairs.append((user_id.strip(), token.strip()))
    return tuple(pairs)


def resolve_principal(
    token: str | None,
    *,
    legacy_token: str,
) -> Principal | None:
    users = _user_tokens()
    if users:
        if not token:
            return None
        for user_id, expected in users:
            if secrets.compare_digest(token, expected):
                return Principal(user_id, "user-token")
        return None
    if legacy_token:
        if token and secrets.compare_digest(token, legacy_token):
            return Principal(LOCAL_USER, "legacy-token")
        return None
    return Principal(LOCAL_USER, "local")


def authentication_required(*, legacy_token: str) -> bool:
    return bool(_user_tokens() or legacy_token)
```

- [x] **Step 4: Run GREEN**

Run the Task 1 test command.

Expected: all identity tests pass.

## Task 2: M1a-1 HTTP Principal Context

**Files:**
- Modify: `tests/test_server_identity.py`
- Modify: `coworker/server/app.py`

- [x] **Step 1: Write the HTTP RED**

Add a test-only route after creating the production app:

```python
from fastapi import Request
from fastapi.testclient import TestClient

from coworker.server import SessionManager, create_app


def test_http_auth_attaches_distinct_principals(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:tok-a,bob:tok-b")
    monkeypatch.setenv("COWORKER_API_TOKEN", "legacy")
    app = create_app(SessionManager(data_dir=tmp_path / "state"))

    @app.get("/_test/principal")
    def principal(request: Request) -> dict[str, str]:
        return {
            "user_id": request.state.principal.user_id,
            "via": request.state.principal.via,
        }

    client = TestClient(app)
    assert client.get(
        "/_test/principal", headers={"X-OpenWorker-Token": "tok-a"}
    ).json() == {"user_id": "alice", "via": "user-token"}
    assert client.get(
        "/_test/principal", headers={"X-OpenWorker-Token": "tok-b"}
    ).json() == {"user_id": "bob", "via": "user-token"}
    assert client.get(
        "/_test/principal", headers={"X-OpenWorker-Token": "legacy"}
    ).status_code == 401
```

Also assert tokenless health stays minimal and an authenticated health request returns the existing full payload.

- [x] **Step 2: Run RED**

Expected: requests using `tok-a` and `tok-b` return 401 because the current middleware accepts only `COWORKER_API_TOKEN`.

- [x] **Step 3: Implement HTTP identity attachment**

In `create_app`, resolve the header through `resolve_principal(..., legacy_token=api_token)`.
For non-tokenless, non-OPTIONS requests:

```python
principal = _request_principal(request)
if principal is None:
    return JSONResponse(
        {"error": "missing or invalid OpenWorker sidecar token"},
        status_code=401,
    )
request.state.principal = principal
return await call_next(request)
```

Keep tokenless callbacks unchanged. Health may call `_request_principal` only to decide whether to return the full payload; it must not require `request.state.principal`.

- [x] **Step 4: Run GREEN**

Run:

```bash
.venv/bin/pytest -q tests/test_server_identity.py tests/test_server.py::test_sidecar_token_gates_rest_and_websockets
```

Expected: all selected tests pass.

## Task 3: M1a-1 WebSocket Principal Context

**Files:**
- Modify: `tests/test_server_identity.py`
- Modify: `coworker/server/app.py`

- [x] **Step 1: Write WebSocket RED**

```python
def test_websocket_accepts_each_user_token_and_rejects_legacy(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:tok-a,bob:tok-b")
    monkeypatch.setenv("COWORKER_API_TOKEN", "legacy")
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "state")))

    for token in ("tok-a", "tok-b"):
        with client.websocket_connect(
            "/ws/events", subprotocols=["openworker", token]
        ) as websocket:
            assert websocket.accepted_subprotocol == "openworker"

    with pytest.raises(WebSocketDisconnect) as denied:
        with client.websocket_connect(
            "/ws/events", subprotocols=["openworker", "legacy"]
        ) as websocket:
            websocket.receive_text()
    assert denied.value.code == 1008
```

- [x] **Step 2: Run RED**

Expected: `tok-a` and `tok-b` are rejected by the current single-token comparison.

- [x] **Step 3: Implement WebSocket identity attachment**

Replace the boolean helper with a principal-returning helper. At both WebSocket entries:

1. Reject a disallowed Origin.
2. Resolve the token from offered subprotocols.
3. Close with 1008 when no principal resolves.
4. Assign `ws.state.principal`.
5. Preserve `accept(subprotocol="openworker")` whenever authentication is configured.

Do not return a user token in the accepted subprotocol.

- [x] **Step 4: Run GREEN**

Run the Task 3 test and the existing origin/token WebSocket tests.

Expected: all pass.

## Task 4: M1a-1 Regression and Documentation

**Files:**
- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [x] **Step 1: Run focused backend regression**

```bash
.venv/bin/pytest -q \
  tests/test_server_identity.py \
  tests/test_alpha_mode.py \
  tests/test_cloud_server.py \
  tests/test_server.py
```

- [x] **Step 2: Run required project checks**

```bash
.venv/bin/python -m coworker.server.run --help
.venv/bin/python -m extensions.career_mcp.crawl_cli --list
cd surfaces/gui && npx tsc --noEmit
cd ../.. && SKIP_NPM_CI=1 bash deploy/build-frontend.sh
git diff --check
```

- [x] **Step 3: Confirm security invariants**

```bash
rg -n "re.escape|OPENCAR_EXTRA_ORIGINS" coworker/server/app.py deploy
rg -n "MODE === \\"alpha\\"|apiToken" surfaces/gui/src/api.ts
git status --short -- deploy/.env deploy/web
```

Expected: exact Origin matching remains; Alpha token remains absent from frontend; secrets and generated web assets remain untracked.

- [x] **Step 4: Record evidence**

Append exact RED/GREEN results, regression totals and the fact that M1a-1 does not yet provide storage isolation. Mark M1a-2 as the next Gate.

## Subsequent Stage Gates

Do not execute these until the previous Gate is deployed and verified.

1. **M0 production baseline:** Docker build, IP Compose, health, authenticated REST, WS 101, Alpha 403 restrictions and a脱敏 resume smoke.
2. **M1a-2 Career isolation:** validated per-user `CareerConfig`, private resume paths and cross-token 404 tests.
3. **M1a-3 runtime isolation:** bounded `ManagerRegistry`, user-specific OpenWorker state/workspace, MCP subprocess environment verification and memory measurements.
4. **M1a-4 deployment consolidation:** one backend, shared user root, exact Origin list, migration and rollback.
5. **M1b:** verified JWT identity, then Postgres/object storage/RLS. Do not combine M1b with M1a.
