"""Local owner extensions must never change the public Career boundary."""
from pathlib import Path
import asyncio
import pytest
from fastapi.testclient import TestClient
from coworker.server import SessionManager,create_app,alpha
from coworker.server import local_access


def setup(tmp_path,monkeypatch,local=True):
    workspace=tmp_path/'managed';workspace.mkdir()
    monkeypatch.setenv('OPENCAR_ALPHA_TEST','1');monkeypatch.setenv('OPENCAR_ALPHA_WORKSPACE',str(workspace))
    for key in ['OPENCAR_LOCAL_MODE','OPENCAR_LOCAL_ACCESS']:
        monkeypatch.setenv(key,'1' if local else '0')
    manager=SessionManager(workspace=workspace);manager.personas.set_enabled('career',True)
    async def no_mcp(*a,**kw):return []
    monkeypatch.setattr(manager,'prepare_mcp_tools',no_mcp)
    return manager,TestClient(create_app(manager)),workspace


def test_public_and_local_routes_stay_separate(tmp_path,monkeypatch):
    manager,client,workspace=setup(tmp_path,monkeypatch,local=False)
    for method,path in [('GET','/v1/connectors'),('POST','/v1/sessions/a/roots'),('POST','/v1/sessions/a/connections')]:
        assert client.request(method,path,json={}).status_code==403

    monkeypatch.setenv('OPENCAR_LOCAL_MODE','1');assert client.get('/v1/connectors').status_code==403
    monkeypatch.setenv('OPENCAR_LOCAL_ACCESS','1');assert client.get('/v1/connectors').status_code==200
    assert all(not row['managed'] for row in client.get('/v1/connectors').json()['connectors'])
    assert client.get('/mcp/oauth/callback',params={'code':'invalid','state':'invalid'}).status_code==400
    assert client.post('/v1/connectors/slack/connect-managed',json={}).status_code==403
    for method,path in [('POST','/v1/mcp'),('PUT','/v1/mcp'),('POST','/v1/workspaces/trust'),('POST','/v1/personas/install'),('POST','/v1/automations')]:
        assert client.request(method,path,json={}).status_code==403


@pytest.mark.parametrize('local',[False,True])
def test_multiple_local_tabs_do_not_exhaust_the_public_polling_budget(tmp_path,monkeypatch,local):
    monkeypatch.setattr('coworker.server.cloud_security.monotonic',lambda:1.0)
    manager,client,_=setup(tmp_path,monkeypatch,local=local)
    # A real request through the middleware, matching background polling shared
    # by tabs under one local owner. The hosted boundary remains 180/minute.
    for _ in range(180):
        assert client.get('/v1/agents').status_code==200
    response=client.get('/v1/agents')
    assert response.status_code==(200 if local else 429)
    if not local:assert response.headers['Retry-After']=='60'


def test_scoped_files_live_browser_switch_and_restart(tmp_path,monkeypatch):
    manager,client,workspace=setup(tmp_path,monkeypatch)
    docs=tmp_path/'documents';docs.mkdir();(docs/'resume.txt').write_text('Fictitious experience')
    outside=tmp_path/'outside';outside.mkdir();(outside/'private.txt').write_text('not granted')
    response=client.post('/v1/sessions/local/roots',json={'path':str(docs)})
    assert response.json()['ok'] is True
    record=manager.session_store.load('local');assert record.agent=='career';assert record.workspace==str(workspace)
    engine=manager.get_engine('local',agent='career',workspace=str(workspace));assert engine is not None
    names=set(engine.registry.names())
    assert {'browser_open_url','browser_read_url','read_file','write_file'}<=names
    assert not ({'run_shell','shell','save_skill','delete_file'} & names)
    assert engine.roots[0].path != workspace and engine.roots[0].path.is_relative_to(tmp_path)
    assert engine.roots[1].path==docs and engine.roots[1].writable is False
    assert 'Fictitious experience' in str(engine.registry.execute('read_file',{'path':str(docs/'resume.txt')}))
    with pytest.raises(PermissionError):
        engine.registry.execute('read_file',{'path':str(outside/'private.txt')})
    with pytest.raises(PermissionError):
        engine.registry.execute('write_file',{'path':str(docs/'no.txt'),'content':'no'})
    assert not (docs/'no.txt').exists()
    (docs/'escape.txt').symlink_to(outside/'private.txt')
    with pytest.raises(PermissionError):
        engine.registry.execute('read_file',{'path':str(docs/'escape.txt')})
    engine.registry.execute('write_file',{'path':'result.txt','content':'local result'})
    assert client.get('/v1/sessions/local/artifacts').json()['artifacts'][0]['name']=='result.txt'
    assert client.get('/v1/sessions/local/artifacts/read',params={'path':'result.txt'}).json()['ok']
    assert client.get('/v1/sessions/local/artifacts/read',params={'path':str(workspace/'mcp.json')}).json()['ok'] is False
    assert client.post('/v1/sessions/local/connections',json={'connector':'browser','enabled':False}).json()['ok']
    assert 'browser_open_url' not in engine.registry.names()
    assert client.post('/v1/sessions/local/connections',json={'connector':'browser','enabled':True}).json()['ok']
    assert 'browser_open_url' in engine.registry.names()
    assert client.post('/v1/sessions/local/roots',json={'path':str(docs),'writable':True}).json()['ok']
    assert engine.roots[1].writable is True
    engine.registry.execute('write_file',{'path':str(docs/'allowed.txt'),'content':'test'})
    assert (docs/'allowed.txt').read_text()=='test'
    for protected in [workspace,Path(__file__).resolve().parents[1],tmp_path]:
        assert client.post('/v1/sessions/local/roots',json={'path':str(protected),'writable':True}).json()['ok'] is False
    restored=SessionManager(workspace=workspace);restored.personas.set_enabled('career',True)
    resumed=restored.get_engine('local',agent='career');assert resumed.roots[1].path==docs and resumed.roots[1].writable
    assert client.delete('/v1/sessions/local/roots',params={'path':str(docs)}).json()['ok']
    assert not any(r.path==docs for r in engine.roots)
    with pytest.raises(PermissionError):
        engine.registry.execute('read_file',{'path':str(docs/'resume.txt')})


def test_connected_service_tools_refresh_without_enabling_host_commands(tmp_path,monkeypatch):
    from coworker.connectors.setup import connect_connector
    manager,client,workspace=setup(tmp_path,monkeypatch)
    engine=manager.get_engine('service',agent='career',workspace=str(workspace))
    # Only credential validation is mocked. No third-party API receives this fixture.
    monkeypatch.setattr(manager,'connect_connector',lambda name,fields,**kw:
        connect_connector(manager.secrets,name,fields,validate=False))
    assert client.post('/v1/connectors/github/connect',json={'fields':{'token':'fictional-local-test'}}).json()['ok']
    assert 'github_search' in engine.registry.names()
    assert not ({'github_clone','github_pull'} & set(engine.registry.names()))
    assert client.post('/v1/sessions/service/connections',json={'connector':'github','enabled':False}).json()['ok']
    assert 'github_search' not in engine.registry.names()
    assert client.post('/v1/sessions/service/connections',json={'connector':'github','enabled':True}).json()['ok']
    assert 'github_search' in engine.registry.names()
    assert client.patch('/v1/connectors/github/tools',json={'enabled':{'github_search':False}}).json()['ok']
    assert 'github_search' not in engine.registry.names()
