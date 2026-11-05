"""No real accounts, QR approvals, or external messages in automatic tests."""
import json
from urllib.parse import parse_qs
import httpx
import pytest
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.feishu_pairing import FeishuPairing
from extensions.career_mcp.services.job_subscriptions import JobSubscriptions
from extensions.career_mcp.services.job_notifications import BotSender


def test_official_scan_pairing_keeps_credentials_private_and_bound_to_scan_owner(tmp_path,caplog):
    calls=[];clock=[1000.0]
    def handle(request):
        body=parse_qs(request.content.decode());calls.append(body)
        assert str(request.url)=='https://accounts.feishu.cn/oauth/v1/app/registration'
        if body['action']==['init']:return httpx.Response(200,json={'supported_auth_methods':['client_secret']})
        if body['action']==['begin']:
            assert body['archetype']==['PersonalAgent'] and body['request_user_info']==['open_id']
            return httpx.Response(200,json={'device_code':'fixture-device-private','verification_uri_complete':'https://accounts.feishu.cn/fixture?user_code=public-code','interval':5,'expire_in':600})
        return httpx.Response(200,json={'client_id':'cli_fixture','client_secret':'fixture-secret-private','user_info':{'open_id':'ou_fixtureowner'}})
    service=JobSubscriptions(CareerConfig(tmp_path/'career'))
    pair=FeishuPairing(service,transport=httpx.MockTransport(handle),clock=lambda:clock[0])
    begun=pair.begin()
    assert begun['qr_image'].startswith('data:image/svg+xml;base64,')
    assert 'fixture-device-private' not in json.dumps(begun)
    assert pair.poll(begun['session_id'])['state']=='pending' and len(calls)==2
    clock[0]+=5
    connected=pair.poll(begun['session_id'])
    assert connected['state']=='connected' and connected['channel']['kind']=='feishu_app'
    assert pair.poll(begun['session_id'])==connected and len(service.channels())==1
    assert FeishuPairing(JobSubscriptions(CareerConfig(tmp_path/'other')),clock=lambda:clock[0]).poll(begun['session_id'])['state']=='expired'
    assert 'fixture-secret-private' not in json.dumps(connected)+json.dumps(service.channels())+caplog.text
    channel=connected['channel'];secret=service.secrets.get('job-push:'+channel['id'])
    assert secret['open_id']=='ou_fixtureowner'
    sent=[]
    def sender(req):
        sent.append(str(req.url))
        assert req.url.host=='open.feishu.cn'
        if req.url.path.endswith('/internal'):return httpx.Response(200,json={'code':0,'tenant_access_token':'fixture-token-private'})
        body=json.loads(req.content)
        assert body['receive_id']=='ou_fixtureowner' and json.loads(body['content'])['text']=='OpenCareer 测试'
        assert req.headers['Authorization']=='Bearer fixture-token-private'
        return httpx.Response(200,json={'code':0})
    assert BotSender(transport=httpx.MockTransport(sender),resolve=False).send('feishu_app',secret,'OpenCareer 测试')=='sent'
    assert len(sent)==2


@pytest.mark.parametrize('outcome',['expired_token','access_denied','slow_down'])
def test_expiry_refusal_and_rate_limit_are_explicit(tmp_path,outcome):
    now=[0.0]
    def response(req):
        action=parse_qs(req.content.decode())['action'][0]
        return httpx.Response(200,json=({'supported_auth_methods':['client_secret']} if action=='init' else {'device_code':'private','verification_uri_complete':'https://accounts.feishu.cn/scan','expire_in':30} if action=='begin' else {'error':outcome}))
    pair=FeishuPairing(JobSubscriptions(CareerConfig(tmp_path/'career')),transport=httpx.MockTransport(response),clock=lambda:now[0])
    sid=pair.begin()['session_id'];now[0]=6
    result=pair.poll(sid)
    assert result['state']=={'expired_token':'expired','access_denied':'cancelled','slow_down':'pending'}[outcome]
    now[0]=35
    assert pair.poll(sid)['state']=='expired'


def test_untrusted_authorization_url_and_missing_owner_cannot_connect(tmp_path):
    def response(req):
        action=parse_qs(req.content.decode())['action'][0]
        return httpx.Response(200,json={'supported_auth_methods':['client_secret']} if action=='init' else {'device_code':'private','verification_uri_complete':'https://evil.example/scan'})
    service=JobSubscriptions(CareerConfig(tmp_path/'career'))
    with pytest.raises(ValueError,match='授权地址'):
        FeishuPairing(service,transport=httpx.MockTransport(response)).begin()
    with pytest.raises(ValueError):service.save_feishu_app('cli_fixture','fixture-secret',None)
    assert not service.channels()


def test_cancel_prevents_late_pairing_and_message_timeout_is_uncertain(tmp_path):
    def response(req):
        action=parse_qs(req.content.decode())['action'][0]
        return httpx.Response(200,json={'supported_auth_methods':['client_secret']} if action=='init' else {'device_code':'private','verification_uri_complete':'https://accounts.feishu.cn/scan'})
    service=JobSubscriptions(CareerConfig(tmp_path/'career'));pair=FeishuPairing(service,transport=httpx.MockTransport(response))
    sid=pair.begin()['session_id'];pair.cancel(sid)
    assert pair.poll(sid)['state']=='expired' and not service.channels()
    def sender(req):
        if req.url.path.endswith('/internal'):return httpx.Response(200,json={'code':0,'tenant_access_token':'secret'})
        raise httpx.ReadTimeout('private-token',request=req)
    assert BotSender(transport=httpx.MockTransport(sender),resolve=False).send('feishu_app',{'app_id':'cli_fixture','app_secret':'private','open_id':'ou_fixture'},'message')=='uncertain'


def test_cancel_during_pending_network_poll_cannot_save_late_credentials(tmp_path):
    import threading
    waiting=threading.Event();release=threading.Event();clock=[0.0]
    def handler(request):
        action=parse_qs(request.content.decode())['action'][0]
        if action=='init':return httpx.Response(200,json={'supported_auth_methods':['client_secret']})
        if action=='begin':return httpx.Response(200,json={'device_code':'private','verification_uri_complete':'https://accounts.feishu.cn/scan'})
        waiting.set();assert release.wait(5)
        return httpx.Response(200,json={'client_id':'cli_fixture','client_secret':'private-secret','user_info':{'open_id':'ou_fixture'}})
    service=JobSubscriptions(CareerConfig(tmp_path/'career'));pair=FeishuPairing(service,transport=httpx.MockTransport(handler),clock=lambda:clock[0])
    sid=pair.begin()['session_id'];clock[0]=6;outcome=[]
    worker=threading.Thread(target=lambda:outcome.append(pair.poll(sid)));worker.start()
    assert waiting.wait(5)
    pair.cancel(sid);release.set();worker.join(5)
    assert outcome==[{'state':'expired'}] and not service.channels()


def test_policy_denial_is_diagnostic_and_never_reaches_message_send(caplog):
    import logging
    calls=[]
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200,json={'code':21001,'msg':'private-secret-private-token'},headers={'x-tt-logid':'fixture-trace'})
    sender=BotSender(transport=httpx.MockTransport(handler),resolve=False)
    credentials={'app_id':'cli_fixture','app_secret':'private-secret','open_id':'ou_fixture'}
    caplog.set_level(logging.DEBUG)
    checked=sender.check_feishu_app(credentials)
    assert checked['status']=='failed' and checked['diagnostic']['reason']=='policy_denied'
    assert checked['diagnostic']['platform_code']==21001 and checked['diagnostic']['request_id']=='fixture-trace'
    assert '豆包' in checked['diagnostic']['message']
    tested=sender.send_with_diagnostics('feishu_app',credentials,'not sent')
    assert tested['status']=='failed' and tested['diagnostic']['stage']=='token'
    assert len(calls)==2 and all('/auth/v3/' in url for url in calls)
    assert 'private-secret' not in json.dumps([checked,tested])+caplog.text and 'private-token' not in json.dumps([checked,tested])+caplog.text


def test_ready_token_check_does_not_certify_message_delivery():
    calls=[]
    def handler(request):
        calls.append(str(request.url));return httpx.Response(200,json={'code':0,'tenant_access_token':'private-token'})
    result=BotSender(transport=httpx.MockTransport(handler),resolve=False).check_feishu_app({'app_id':'cli_fixture','app_secret':'private'})
    assert result['status']=='token_ready' and len(calls)==1
    assert '未发送消息' in result['diagnostic']['message'] and 'private-token' not in json.dumps(result)


def test_unknown_message_ack_is_uncertain_not_retryable():
    def handler(request):
        return httpx.Response(200,json={'code':0,'tenant_access_token':'private'}) if '/auth/v3/' in request.url.path else httpx.Response(200,json={})
    result=BotSender(transport=httpx.MockTransport(handler),resolve=False).send_with_diagnostics('feishu_app',{'open_id':'ou_fixture'},'test')
    assert result['status']=='uncertain' and result['diagnostic']['reason']=='uncertain'
