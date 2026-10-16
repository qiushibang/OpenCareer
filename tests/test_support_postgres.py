"""Real cloud support workflow on a guarded, isolated PostgreSQL database."""
import os
import json
import time
from urllib.error import URLError
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from coworker.server import SessionManager, create_app
from coworker.server.identity import Principal
from coworker.storage.postgres.database import CloudDatabase
from deploy.test_database import validated_test_database_url
from extensions.support.diagnostics import DiagnosticStore


def test_postgres_support_roles_remain_isolated_across_pool_reuse(tmp_path, monkeypatch, capsys):
    url = os.environ.get("TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("isolated TEST_DATABASE_URL required")
    database = CloudDatabase.from_url(validated_test_database_url(url), min_size=1, max_size=1)
    with database.pool.connection() as connection:
        role = connection.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user").fetchone()
        if role != (False, False):
            database.close()
            raise RuntimeError("support isolation tests require a non-superuser, non-bypassrls role")
    database.migrate()
    suffix = uuid4().hex[:12]
    users = [f"support-test-{name}-{suffix}" for name in ("alice", "bob", "admin")]
    for uid in users:
        with database.transaction(Principal(uid, "fixture")) as connection:
            connection.execute("INSERT INTO identity.users(id) VALUES (%s)", (uid,))
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", ",".join(f"{uid}:{name}-fixture" for uid, name in zip(users, ("alice", "bob", "admin"))))
    monkeypatch.setenv("OPENCAR_SUPPORT_ADMIN_IDS", users[2])
    anonymous_id = None
    try:
        store = DiagnosticStore(database=database)
        client = TestClient(create_app(SessionManager(workspace=tmp_path), diagnostic_store=store))
        alice, bob, admin = ({"X-OpenWorker-Token": name + "-fixture"} for name in ("alice", "bob", "admin"))
        request_id = client.post("/v1/support/diagnostics", json={"kind": "page_crash"}, headers=alice).json()["request_id"]
        body = {"kind": "bug", "description": "虚构数据库验收问题", "nonce": uuid4().hex, "request_id": request_id}
        response = client.post("/v1/support/feedback", json=body, headers=alice)
        assert response.status_code == 201
        item = response.json()["feedback"]
        assert client.get(f"/v1/support/diagnostics/{request_id}", headers=bob).status_code == 404
        assert client.get("/v1/support/feedback", headers=bob).json()["feedback"] == []
        detail = client.get(f"/v1/support/admin/feedback/{item['id']}", headers=admin)
        assert detail.status_code == 200
        assert detail.json()["diagnostic"]["request_id"] == request_id
        updated = client.patch(f"/v1/support/admin/feedback/{item['id']}", json={"status": "resolved", "reply": "虚构回复：已修复", "expected_updated_at": item["updated_at"]}, headers=admin)
        assert updated.status_code == 200
        # Reuse the same single connection after the privileged transaction.
        assert client.get("/v1/support/admin/feedback", headers=bob).status_code == 403
        assert client.get(f"/v1/support/feedback/{item['id']}", headers=bob).status_code == 404
        assert client.get(f"/v1/support/feedback/{item['id']}", headers=alice).json()["feedback"]["reply"] == "虚构回复：已修复"
        anonymous = client.post("/v1/support/anonymous-feedback", json={"kind": "bug", "description": "虚构匿名登录问题", "nonce": uuid4().hex})
        assert anonymous.status_code == 201
        anonymous_id = anonymous.json()["feedback"]["id"]
        assert client.get(f"/v1/support/feedback/{anonymous_id}", headers=alice).status_code == 404
        assert client.get(f"/v1/support/admin/feedback/{anonymous_id}", headers=admin).status_code == 200
        # The independent public CLI persists alert cooldown across separate runs/pools.
        from extensions.support.watchdog import main
        prior_alerts = client.get("/v1/support/admin/alerts", headers=admin).json()["alerts"]
        now = max([time.time()] + [item["last_notified_at"] for item in prior_alerts]) + 1800
        monkeypatch.setattr("time.time", lambda: now)
        def offline(*args, **kwargs):
            raise URLError("fictional-private-health-secret")
        monkeypatch.setattr("urllib.request.OpenerDirector.open", offline)
        memory = tmp_path / "watchdog-meminfo"
        memory.write_text("MemTotal: 100 kB\nMemAvailable: 5 kB\n")
        env = {"DATABASE_URL": url, "OPENCAR_SUPPORT_ADMIN_IDS": users[2],
               "OPENCAR_SUPPORT_WATCHDOG_ADMIN_ID": users[2],
               "OPENCAR_WATCHDOG_DISK_PATH": str(tmp_path),
               "OPENCAR_WATCHDOG_MEMINFO_PATH": str(memory)}
        arguments = ["--state-file", str(tmp_path / "watchdog-state.json")]
        capsys.readouterr()
        assert main(arguments, environ=env) == 0
        first = capsys.readouterr().out
        assert "fictional-private-health-secret" not in first
        event = next(item for item in json.loads(first)["events"] if item["category"] == "health_down")
        assert set(event) == {"id", "category", "count"}
        env["OPENCAR_WATCHDOG_MEMINFO_PATH"] = str(tmp_path / "missing-meminfo")
        assert main(arguments, environ=env) == 0
        assert json.loads(capsys.readouterr().out)["events"] == []
        alerts = client.get("/v1/support/admin/alerts", headers=admin).json()["alerts"]
        assert next(item for item in alerts if item["category"] == "memory_pressure")["active"] is True
    finally:
        # Only remove exact fictional rows created by this guarded test.
        if anonymous_id:
            with database.transaction(Principal(users[2], "fixture")) as connection:
                connection.execute("SELECT set_config('app.support_admin', %s, true)", (users[2],))
                connection.execute("DELETE FROM support.feedback WHERE id=%s AND user_id IS NULL", (anonymous_id,))
        for uid in users:
            with database.transaction(Principal(uid, "fixture")) as connection:
                connection.execute("DELETE FROM identity.users WHERE id=%s", (uid,))
        database.close()
