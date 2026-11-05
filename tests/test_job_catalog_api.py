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


def test_scan_routes_stay_local_and_do_not_return_private_credentials(tmp_path,monkeypatch):
    app=client(tmp_path,monkeypatch,local=False)
    assert app.post('/v1/career/job-subscriptions/feishu-pairing').status_code==404
    app=client(tmp_path,monkeypatch)
    sid='a'*48
    assert app.post('/v1/career/job-subscriptions/feishu-pairing/'+sid+'/poll').json()['data']['state']=='expired'
    assert app.delete('/v1/career/job-subscriptions/feishu-pairing/'+sid).status_code==200
    monkeypatch.setenv('DATABASE_URL','postgresql://unused.invalid')
    assert app.post('/v1/career/job-subscriptions/feishu-pairing').status_code==404


def test_connection_check_is_local_only_and_does_not_send_a_message(tmp_path,monkeypatch):
    from extensions.career_mcp.services.job_subscriptions import JobSubscriptions
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.services.job_notifications import BotSender
    app=client(tmp_path,monkeypatch)
    channel=JobSubscriptions(CareerConfig(tmp_path/'career')).save_feishu_app('cli_fixture','fixture-private-secret','ou_fixture')
    def check(sender,credentials):
        assert credentials['app_secret']=='fixture-private-secret'
        return {'status':'failed','diagnostic':{'stage':'token','platform_code':21001,'reason':'policy_denied','message':'访问策略拒绝'}}
    monkeypatch.setattr(BotSender,'check_feishu_app',check)
    monkeypatch.setattr(BotSender,'send',lambda *args:(_ for _ in ()).throw(AssertionError('check must not send')))
    path='/v1/career/job-subscriptions/channels/'+channel['id']+'/check'
    response=app.post(path,json={})
    assert response.status_code==200 and response.json()['data']['diagnostic']['platform_code']==21001
    assert 'fixture-private-secret' not in response.text
    monkeypatch.setenv('OPENCAR_LOCAL_MODE','0')
    assert app.post(path,json={}).status_code==404
