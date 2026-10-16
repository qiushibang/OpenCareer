"""Feedback isolation and state through the authenticated HTTP interface."""
from fastapi.testclient import TestClient
from coworker.server import SessionManager, create_app


def test_user_can_submit_and_reload_only_own_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,bob:bob-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    alice = {"X-OpenWorker-Token": "alice-fixture"}
    bob = {"X-OpenWorker-Token": "bob-fixture"}
    body = {"kind": "bug", "description": "虚构故障：模拟面试无法开始", "nonce": "a" * 32}
    created = client.post("/v1/support/feedback", json=body, headers=alice)
    assert created.status_code == 201
    item = created.json()["feedback"]
    assert item["status"] == "open"
    assert item["description"] == body["description"]
    assert client.post("/v1/support/feedback", json=body, headers=alice).json()["feedback"]["id"] == item["id"]
    assert client.get("/v1/support/feedback", headers=alice).json()["feedback"][0]["id"] == item["id"]
    assert client.get("/v1/support/feedback", headers=bob).json()["feedback"] == []
    assert client.get(f"/v1/support/feedback/{item['id']}", headers=bob).status_code == 404
    assert client.get(f"/v1/support/feedback/{item['id']}", headers=alice).json()["feedback"]["description"] == body["description"]


def test_feedback_rejects_forged_owner_status_and_other_users_diagnostic(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,bob:bob-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    alice = {"X-OpenWorker-Token": "alice-fixture"}
    bob = {"X-OpenWorker-Token": "bob-fixture"}
    diagnostic = client.post("/v1/support/diagnostics", json={"kind": "page_crash"}, headers=alice).json()["request_id"]
    body = {"kind": "bug", "description": "<script>虚构问题</script>", "nonce": "b" * 32, "request_id": diagnostic}
    assert client.post("/v1/support/feedback", json=body, headers=bob).status_code == 409
    assert client.post("/v1/support/feedback", json={**body, "user_id": "bob", "status": "resolved"}, headers=alice).status_code == 422
    created = client.post("/v1/support/feedback", json=body, headers=alice)
    assert created.status_code == 201
    assert created.json()["feedback"]["request_id"] == diagnostic
    assert client.post("/v1/support/feedback", json={**body, "description": "更改过的虚构反馈"}, headers=alice).status_code == 409
    assert client.get("/v1/support/admin/feedback", headers=alice).status_code == 403
    import time
    now = time.time()
    monkeypatch.setattr("time.time", lambda: now + 15 * 86400)
    replay = client.post("/v1/support/feedback", json=body, headers=alice)
    assert replay.status_code == 201
    assert replay.json()["feedback"]["id"] == created.json()["feedback"]["id"]
    assert client.post("/v1/support/feedback", json={**body, "nonce": "2" * 32}, headers=alice).status_code == 409


def test_login_page_intake_is_separate_bounded_and_cannot_read_account_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    body = {"kind": "bug", "description": "虚构登录问题：无法收到验证码", "nonce": "c" * 32}
    response = client.post("/v1/support/anonymous-feedback", json=body)
    assert response.status_code == 201
    assert set(response.json()["feedback"]) == {"id"}
    assert client.post("/v1/support/anonymous-feedback", json=body).json()["feedback"]["id"] == response.json()["feedback"]["id"]
    assert client.get("/v1/support/feedback").status_code == 401
    assert client.get("/v1/support/feedback", headers={"X-OpenWorker-Token": "alice-fixture"}).json()["feedback"] == []
    assert client.post("/v1/support/anonymous-feedback", json={**body, "request_id": "a" * 32}).status_code == 422
    assert client.post("/v1/support/anonymous-feedback", content=b" " * 8193).status_code == 413


def test_designated_admin_can_reply_without_granting_other_users_admin_access(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,bob:bob-fixture,admin:admin-fixture")
    monkeypatch.setenv("OPENCAR_SUPPORT_ADMIN_IDS", "admin")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    alice = {"X-OpenWorker-Token": "alice-fixture"}
    bob = {"X-OpenWorker-Token": "bob-fixture"}
    admin = {"X-OpenWorker-Token": "admin-fixture"}
    item = client.post("/v1/support/feedback", json={"kind": "bug", "description": "虚构问题：登录按钮不可用", "nonce": "d" * 32}, headers=alice).json()["feedback"]
    assert client.get("/v1/support/admin/feedback").status_code == 401
    assert client.get("/v1/support/admin/feedback", headers=bob).status_code == 403
    assert client.get("/v1/support/capabilities", headers=bob).json()["admin"] is False
    assert client.get("/v1/support/capabilities", headers=admin).json()["admin"] is True
    listing = client.get("/v1/support/admin/feedback", headers=admin)
    assert listing.status_code == 200
    assert listing.json()["feedback"][0]["id"] == item["id"]
    path = f"/v1/support/admin/feedback/{item['id']}"
    update = {"status": "resolved", "reply": "虚构回复：已修复，请刷新重试", "expected_updated_at": item["updated_at"]}
    assert client.patch(path, json=update, headers=bob).status_code == 403
    assert client.patch(path, json=update, headers=admin).status_code == 200
    own = client.get(f"/v1/support/feedback/{item['id']}", headers=alice).json()["feedback"]
    assert own["status"] == "resolved" and own["reply"] == update["reply"]
    assert "user_id" not in own
    assert client.patch(path, json=update, headers=admin).status_code == 409


def test_admin_can_inspect_and_merge_without_disclosing_other_users_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,bob:bob-fixture,admin:admin-fixture")
    monkeypatch.setenv("OPENCAR_SUPPORT_ADMIN_IDS", "admin")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    alice, bob, admin = ({"X-OpenWorker-Token": value + "-fixture"} for value in ("alice", "bob", "admin"))
    diagnostic = client.post("/v1/support/diagnostics", json={"kind": "page_crash"}, headers=alice).json()["request_id"]
    source = client.post("/v1/support/feedback", json={"kind": "bug", "description": "虚构来源问题：页面崩溃", "nonce": "e" * 32, "request_id": diagnostic}, headers=alice).json()["feedback"]
    target = client.post("/v1/support/feedback", json={"kind": "bug", "description": "bob-private-fixture-description", "nonce": "f" * 32}, headers=bob).json()["feedback"]
    detail = client.get(f"/v1/support/admin/feedback/{source['id']}", headers=admin)
    assert detail.status_code == 200
    assert detail.json()["diagnostic"]["request_id"] == diagnostic
    path = f"/v1/support/admin/feedback/{source['id']}/merge"
    assert client.post(path, json={"target_id": target["id"], "expected_updated_at": source["updated_at"]}, headers=admin).status_code == 200
    own = client.get(f"/v1/support/feedback/{source['id']}", headers=alice)
    assert own.json()["feedback"]["status"] == "merged"
    assert "bob-private-fixture-description" not in own.text and target["id"] not in own.text
    audit = client.get("/v1/support/admin/audit", headers=admin)
    assert audit.status_code == 200
    assert "merge" in audit.text
    assert "bob-private-fixture-description" not in audit.text
    assert "页面崩溃" not in audit.text
    assert client.get("/v1/support/admin/audit", headers=alice).status_code == 403
    third = client.post("/v1/support/feedback", json={"kind": "bug", "description": "虚构第三个重复问题", "nonce": "1" * 32}, headers=alice).json()["feedback"]
    # A main issue with existing children cannot become a child itself: keep replies one-level.
    assert client.post(f"/v1/support/admin/feedback/{target['id']}/merge", json={"target_id": third["id"], "expected_updated_at": target["updated_at"]}, headers=admin).status_code == 409
    reply = "虚构主问题回复：仅适用于 bob 的私密处理说明"
    assert client.patch(f"/v1/support/admin/feedback/{target['id']}", json={"status": "resolved", "reply": reply, "expected_updated_at": target["updated_at"]}, headers=admin).status_code == 200
    updated_source = client.get(f"/v1/support/feedback/{source['id']}", headers=alice)
    assert updated_source.json()["feedback"]["status"] == "resolved"
    assert updated_source.json()["feedback"]["reply"] == "关联问题已修复，请重新尝试；如问题仍存在，请新建反馈。"
    assert reply not in updated_source.text and target["id"] not in updated_source.text
    later_source = client.post("/v1/support/feedback", json={"kind": "bug", "description": "虚构稍后合并的问题", "nonce": "2" * 32}, headers=alice).json()["feedback"]
    immediate = client.post(f"/v1/support/admin/feedback/{later_source['id']}/merge", json={"target_id": target["id"], "expected_updated_at": later_source["updated_at"]}, headers=admin)
    assert immediate.status_code == 200
    assert immediate.json()["feedback"]["status"] == "resolved"
    assert immediate.json()["feedback"]["reply"] == "关联问题已修复，请重新尝试；如问题仍存在，请新建反馈。"
    assert reply not in immediate.text


def test_admin_error_alerts_are_content_free_and_deduplicated(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture,admin:admin-fixture")
    monkeypatch.setenv("OPENCAR_SUPPORT_ADMIN_IDS", "admin")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    alice = {"X-OpenWorker-Token": "alice-fixture"}
    admin = {"X-OpenWorker-Token": "admin-fixture"}
    for _ in range(10):
        assert client.post("/v1/support/diagnostics", json={"kind": "page_crash"}, headers=alice).status_code == 201
    first = client.get("/v1/support/admin/alerts", headers=admin)
    assert first.status_code == 200
    alert = first.json()["alerts"][0]
    assert alert["category"] == "page_crash" and alert["count"] == 10
    assert "alice" not in first.text and "description" not in first.text
    again = client.get("/v1/support/admin/alerts", headers=admin)
    assert len(again.json()["alerts"]) == 1
    assert again.json()["alerts"][0]["id"] == alert["id"]
    assert client.get("/v1/support/admin/alerts", headers=alice).status_code == 403


def test_user_history_supports_bounded_pagination(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_ALPHA_TEST", "1")
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    headers = {"X-OpenWorker-Token": "alice-fixture"}
    ids = []
    for nonce in ("a" * 32, "b" * 32):
        ids.append(client.post("/v1/support/feedback", json={"kind": "suggestion", "description": "虚构建议：增加反馈入口", "nonce": nonce}, headers=headers).json()["feedback"]["id"])
    page = client.get("/v1/support/feedback?limit=1&offset=1", headers=headers)
    assert [item["id"] for item in page.json()["feedback"]] == [ids[0]]
    assert client.get("/v1/support/feedback?limit=1000000", headers=headers).status_code == 422


def test_feedback_keeps_only_server_recognized_ui_release(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCAR_USER_TOKENS", "alice:alice-fixture")
    monkeypatch.setenv("OPENCAR_RELEASE", "fixture-release-20260918")
    client = TestClient(create_app(SessionManager(workspace=tmp_path)))
    response = client.post("/v1/support/feedback", json={"kind": "bug", "description": "虚构页面版本问题", "nonce": "c" * 32, "ui_release": "fictional-private-token"}, headers={"X-OpenWorker-Token": "alice-fixture"})
    assert response.status_code == 201
    assert response.json()["feedback"]["ui_release"] == "unknown"
    assert response.json()["feedback"]["release"] == "fixture-release-20260918"
    assert "fictional-private-token" not in response.text
