from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager


def client(tmp_path, monkeypatch, local=True):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("OPENCAR_LOCAL_MODE", "1" if local else "0")
    return TestClient(create_app(SessionManager(data_dir=tmp_path / "state")))


def test_catalog_and_channels_are_local_only(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch, local=False)
    assert app.get("/v1/career/catalog/schema").status_code == 404
    assert app.get("/v1/career/job-subscriptions/channels").status_code == 404


def test_subscription_preview_and_activation_require_current_version(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    schema = app.get("/v1/career/catalog/schema").json()["data"]
    assert "business_lines" in schema["fields"]
    response = app.post("/v1/career/catalog/search", json={"condition": {"field": "shell", "op": "in", "values": ["rm"]}})
    assert response.status_code == 400
    channel = app.post("/v1/career/job-subscriptions/channels", json={"name": "测试", "kind": "wecom", "url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=fixture"}).json()["data"]
    assert "fixture" not in app.get("/v1/career/job-subscriptions/channels").text
    sub = app.post("/v1/career/job-subscriptions", json={"title": "北京", "channel_ids": [channel["id"]]}).json()["data"]
    url = "/v1/career/job-subscriptions/" + sub["id"]
    assert app.post(url + "/activate", json={"version": sub["version"]}).status_code == 400
    assert app.post(url + "/activate", json={"version": 999, "confirmed": True}).status_code == 400
    assert app.post(url + "/preview", json={}).json()["data"]["total"] == 0
    assert app.post(url + "/activate", json={"version": sub["version"], "confirmed": True}).status_code == 200
    assert app.delete("/v1/career/job-subscriptions/channels/" + channel["id"]).status_code == 400
    assert app.post(url + "/pause").status_code == 200
    assert app.delete("/v1/career/job-subscriptions/channels/" + channel["id"]).status_code == 200


def test_query_result_can_be_read_without_model_output_truncation(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    result = app.post("/v1/career/catalog/search", json={}).json()["data"]
    reread = app.get("/v1/career/catalog/results/" + result["result_id"]).json()["data"]
    assert reread["result_id"] == result["result_id"]
    assert reread["total"] == 0
