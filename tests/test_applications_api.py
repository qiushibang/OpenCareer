from fastapi.testclient import TestClient
from coworker.server.app import create_app
from coworker.server.manager import SessionManager


def client(tmp_path, monkeypatch, *, local=True):
    monkeypatch.setenv("OPENCAR_LOCAL_MODE", "1" if local else "0")
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return TestClient(create_app(SessionManager(data_dir=tmp_path / "state")))


def test_personal_workflow_routes_are_local_only(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch, local=False)
    assert app.post("/v1/career/applications", json={"company":"x","title":"y"}).status_code == 404
    assert app.post("/v1/career/applications/export", json={}).status_code == 404


def test_application_rounds_and_export_use_the_same_local_records(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    record = app.post("/v1/career/applications", json={"company":"测试公司","title":"产品","notes":"旧备注","jd":"职位描述"}).json()["data"]
    path = "/v1/career/applications/"+record["id"]
    assert app.patch(path,json={"expected_version":99,"notes":"不能覆盖"}).status_code == 409
    first = app.post(path+"/interviews",json={"round_name":"业务一面","review":"一面面经","result":"pending"}).json()["data"]
    detail = app.get(path).json()["data"]
    assert detail["status"] == "preparing" and detail["interviews"][0]["result"] == "pending"
    exported = app.post("/v1/career/applications/export",json={"ids":[record["id"]]}).json()["data"]
    assert exported["applications"][0]["notes"] == "旧备注"
    assert exported["interviews"][0]["id"] == first["id"]
    assert "private_path" not in str(exported) and "API_KEY" not in str(exported)
    app2 = client(tmp_path / "other-owner",monkeypatch)
    assert app2.get(path).status_code == 404
    assert app2.post("/v1/career/applications/export",json={"ids":[record["id"]]}).status_code == 400


def test_unknown_fields_cross_application_rounds_and_hosted_database_are_rejected(tmp_path, monkeypatch):
    app=client(tmp_path,monkeypatch)
    one=app.post("/v1/career/applications",json={"company":"一公司","title":"产品"}).json()["data"]
    two=app.post("/v1/career/applications",json={"company":"二公司","title":"产品"}).json()["data"]
    prefix="/v1/career/applications/"
    round=app.post(prefix+one["id"]+"/interviews",json={"round_name":"一面"}).json()["data"]
    assert app.patch(prefix+two["id"]+"/interviews/"+round["id"],json={"expected_version":round["version"],"review":"不能串记录"}).status_code == 404
    assert app.post("/v1/career/applications/query",json={"user_id":"other"}).status_code == 400
    assert app.post("/v1/career/applications",json={"company":"x","title":"y","source_url":"javascript:alert(1)"}).status_code == 400
    assert app.patch(prefix+one["id"],json={"expected_version":one["version"],"owner_id":"other"}).status_code == 400
    monkeypatch.setenv("DATABASE_URL","postgresql://not-used.invalid/test")
    assert app.post("/v1/career/applications/export",json={}).status_code == 404


def test_delete_interview_is_versioned_scoped_and_preserves_other_records(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    base = "/v1/career/applications"
    one = app.post(base,json={"company":"示例一","title":"产品","notes":"原备注"}).json()["data"]
    two = app.post(base,json={"company":"示例二","title":"产品"}).json()["data"]
    path = base+"/"+one["id"]
    first = app.post(path+"/interviews",json={"round_name":"一面","experience_notes":"保留一面"}).json()["data"]
    second = app.post(path+"/interviews",json={"round_name":"二面","experience_notes":"删除二面"}).json()["data"]
    endpoint=path+"/interviews/"+second["id"]
    assert app.request("DELETE",base+"/"+two["id"]+"/interviews/"+second["id"],json={"expected_version":second["version"]}).status_code==404
    assert app.request("DELETE",endpoint,json={"expected_version":99}).status_code==409
    assert app.request("DELETE",endpoint,json={"expected_version":second["version"]}).status_code==200
    detail=app.get(path).json()["data"]
    assert detail["notes"]=="原备注" and detail["status"]=="preparing"
    assert [row["id"] for row in detail["interviews"]]==[first["id"]]
    assert "删除真实面试" in detail["history"][0]["summary"]
    exported=app.post(base+"/export",json={}).json()["data"]
    assert len(exported["interviews"])==1 and "删除二面" not in str(exported)
    assert app.request("DELETE",endpoint,json={"expected_version":second["version"]}).status_code==404
    monkeypatch.setenv("OPENCAR_LOCAL_MODE","0")
    assert app.request("DELETE",path+"/interviews/"+first["id"],json={"expected_version":first["version"]}).status_code==404
