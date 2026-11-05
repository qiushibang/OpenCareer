"""Narrow outbound-only official group robot adapters. No arbitrary URL tool."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import socket
import time
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

ENDPOINTS = {"feishu": ("open.feishu.cn", r"/open-apis/bot/v2/hook/[a-zA-Z0-9_-]+", None),
             "dingtalk": ("oapi.dingtalk.com", r"/robot/send", "access_token"),
             "wecom": ("qyapi.weixin.qq.com", r"/cgi-bin/webhook/send", "key")}

_bot_request = ContextVar("career_private_bot_request", default=False)


class _BotTransportPrivacy(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # HTTP client debug/INFO logs include URL tokens. Keep unrelated traffic visible.
        return not _bot_request.get()


for _logger in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks"):
    logging.getLogger(_logger).addFilter(_BotTransportPrivacy())


@contextmanager
def _private_transport():
    token = _bot_request.set(True)
    try:
        yield
    finally:
        _bot_request.reset(token)


def validate_endpoint(kind: str, url: str) -> str:
    if kind not in ENDPOINTS or not isinstance(url, str) or len(url) > 2048:
        raise ValueError("请选择飞书、钉钉或企业微信官方机器人。")
    host, path, query_key = ENDPOINTS[kind]
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != host or parsed.username or parsed.password or parsed.port not in (None, 443) or parsed.fragment or not re.fullmatch(path, parsed.path):
        raise ValueError("机器人地址必须是该渠道的官方 HTTPS Webhook。")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (query_key is None and parsed.query) or (query_key and (set(query) != {query_key} or len(query[query_key]) != 1 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,500}", query[query_key][0]))):
        raise ValueError("机器人地址参数不正确。")
    return url


class BotSender:
    def __init__(self, *, transport=None, resolve: bool = True, clock=time.time):
        self.transport, self.resolve, self.clock = transport, resolve, clock

    def send(self, kind: str, credentials: dict, message: str) -> str:
        if kind == "feishu_app":
            return self._send_feishu_app(credentials,message)
        url = validate_endpoint(kind, credentials.get("url", ""))
        if self.resolve:
            try:
                addresses = socket.getaddrinfo(urlsplit(url).hostname, 443, type=socket.SOCK_STREAM)
                if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                    return "failed"
            except OSError:
                return "retryable"
        secret = credentials.get("secret") or ""
        payload = {"msg_type": "text", "content": {"text": message}} if kind == "feishu" else {"msgtype": "text", "text": {"content": message}}
        if secret and kind == "feishu":
            stamp = str(int(self.clock()))
            payload.update({"timestamp": stamp, "sign": base64.b64encode(hmac.new((stamp + "\n" + secret).encode(), b"", hashlib.sha256).digest()).decode()})
        elif secret and kind == "dingtalk":
            stamp = str(int(self.clock() * 1000))
            sign = base64.b64encode(hmac.new(secret.encode(), (stamp + "\n" + secret).encode(), hashlib.sha256).digest()).decode()
            parsed = urlsplit(url)
            query = parse_qs(parsed.query)
            query.update({"timestamp": [stamp], "sign": [sign]})
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), ""))
        try:
            with _private_transport(), httpx.Client(transport=self.transport, timeout=10, follow_redirects=False, trust_env=False) as client:
                response = client.post(url, json=payload)
            if response.status_code == 429:
                return "retryable"
            if response.status_code >= 500:
                return "uncertain"
            if response.status_code != 200 or len(response.content) > 64000:
                return "failed"
            result = response.json()
            if not isinstance(result, dict):
                return "failed"
            code = result.get("code") if kind == "feishu" else result.get("errcode")
            if kind == "feishu" and code in {11232, 11233, 11247}:
                return "retryable"
            return "sent" if type(code) is int and code == 0 else "failed"
        except (httpx.TimeoutException, httpx.NetworkError):
            return "uncertain"
        except (ValueError, httpx.HTTPError):
            return "failed"

    @staticmethod
    def _feishu_diagnostic(stage: str, *, response=None, code=None, reason: str = "") -> dict:
        messages = {
            "policy_denied": "飞书访问控制策略拒绝了当前应用（21001），尚未发送消息。请核对扫码使用的账号/空间；若为豆包账号或个人空间，请确认该身份是否支持此应用。团队账号请管理员检查应用可用范围与访问安全策略。重新扫码不保证解除限制。",
            "credentials_rejected": "飞书未签发有效访问凭证，请在开放平台核对应用状态和凭据；尚未发送消息。",
            "token_ready": "已取得飞书访问凭证；连接检查未发送消息，实际投递仍需点击发送测试消息确认。",
            "message_rejected": "飞书消息接口拒绝请求，请核对机器人是否启用/发布、发消息权限及扫码接收人的应用可用范围。",
            "network_unavailable": "暂时无法连接飞书，尚未取得发送凭证；请稍后检查连接。",
            "target_blocked": "飞书地址解析异常，已阻止请求；请检查本机网络或代理设置。",
            "rate_limited": "飞书请求过于频繁，请稍后再试。",
            "uncertain": "消息提交后的结果无法确认。为避免重复消息，请先检查飞书收件箱，再决定是否重试。",
            "sent": "飞书已接受测试消息，请检查本次扫码绑定账号的机器人会话。",
        }
        result = {"stage":stage,"reason":reason,"message":messages.get(reason,"飞书未返回有效结果，请稍后重试。")}
        if response is not None:
            result["http_status"] = response.status_code
            trace = response.headers.get("x-tt-logid", "")
            if re.fullmatch(r"[A-Za-z0-9_-]{1,100}",trace):result["request_id"] = trace
        if type(code) is int:result["platform_code"] = code
        return result

    def _feishu_token(self, client, credentials: dict) -> tuple[str | None, dict]:
        response=client.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",json={"app_id":credentials.get("app_id"),"app_secret":credentials.get("app_secret")})
        if response.status_code==429:
            return None,self._feishu_diagnostic("token",response=response,reason="rate_limited")
        if response.status_code!=200 or len(response.content)>64000:
            return None,self._feishu_diagnostic("token",response=response,reason="credentials_rejected")
        try:data=response.json()
        except ValueError:return None,self._feishu_diagnostic("token",response=response,reason="credentials_rejected")
        if not isinstance(data,dict):return None,self._feishu_diagnostic("token",response=response,reason="credentials_rejected")
        code=data.get("code")
        if type(code) is int and code==0 and isinstance(data.get("tenant_access_token"),str) and data["tenant_access_token"]:
            return data["tenant_access_token"],self._feishu_diagnostic("token",response=response,code=code,reason="token_ready")
        return None,self._feishu_diagnostic("token",response=response,code=code,reason="policy_denied" if code==21001 else "credentials_rejected")

    def _feishu_target(self) -> str | None:
        if not self.resolve:return None
        try:
            addresses=socket.getaddrinfo("open.feishu.cn",443,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):return "target_blocked"
        except OSError:return "network_unavailable"
        return None

    def check_feishu_app(self, credentials: dict) -> dict:
        """Token-only diagnosis. Never calls a messaging endpoint or returns token/body."""
        target=self._feishu_target()
        if target:return {"status":"failed","diagnostic":self._feishu_diagnostic("network",reason=target)}
        try:
            with _private_transport(),httpx.Client(transport=self.transport,timeout=10,follow_redirects=False,trust_env=False) as client:
                token,diagnostic=self._feishu_token(client,credentials)
            return {"status":"token_ready" if token else "failed","diagnostic":diagnostic}
        except (httpx.HTTPError,ValueError):
            return {"status":"failed","diagnostic":self._feishu_diagnostic("token",reason="network_unavailable")}

    def send_with_diagnostics(self, kind: str, credentials: dict, message: str) -> dict:
        if kind!="feishu_app":return {"status":self.send(kind,credentials,message)}
        diagnostic:dict={}
        status=self._send_feishu_app(credentials,message,diagnostic=diagnostic)
        return {"status":status,"diagnostic":diagnostic}

    def _send_feishu_app(self, credentials: dict, message: str, *, diagnostic: dict | None = None) -> str:
        # Fixed platform APIs and bound scan owner only. Never forwards arbitrary targets.
        def finish(status: str, detail: dict) -> str:
            if diagnostic is not None:diagnostic.update(detail)
            return status
        target=self._feishu_target()
        if target:return finish("retryable" if target=="network_unavailable" else "failed",self._feishu_diagnostic("network",reason=target))
        try:
            with _private_transport(),httpx.Client(transport=self.transport,timeout=10,follow_redirects=False,trust_env=False) as client:
                token,detail=self._feishu_token(client,credentials)
                if not token:return finish("retryable" if detail["reason"]=="rate_limited" else "failed",detail)
                try:
                    response=client.post("https://open.feishu.cn/open-apis/im/v1/messages",params={"receive_id_type":"open_id"},headers={"Authorization":"Bearer "+token},json={"receive_id":credentials.get("open_id"),"msg_type":"text","content":json.dumps({"text":message},ensure_ascii=False)})
                except httpx.TransportError:return finish("uncertain",self._feishu_diagnostic("message",reason="uncertain"))
            if response.status_code==429:return finish("retryable",self._feishu_diagnostic("message",response=response,reason="rate_limited"))
            if response.status_code>=500:return finish("uncertain",self._feishu_diagnostic("message",response=response,reason="uncertain"))
            if len(response.content)>64000:
                return finish("uncertain" if response.status_code==200 else "failed",self._feishu_diagnostic("message",response=response,reason="uncertain" if response.status_code==200 else "message_rejected"))
            try:data=response.json()
            except ValueError:
                return finish("uncertain" if response.status_code==200 else "failed",self._feishu_diagnostic("message",response=response,reason="uncertain" if response.status_code==200 else "message_rejected"))
            code=data.get("code") if isinstance(data,dict) else None
            if response.status_code==200 and type(code) is int and code==0:return finish("sent",self._feishu_diagnostic("message",response=response,code=code,reason="sent"))
            if response.status_code==200 and type(code) is not int:return finish("uncertain",self._feishu_diagnostic("message",response=response,reason="uncertain"))
            return finish("failed",self._feishu_diagnostic("message",response=response,code=code,reason="policy_denied" if code==21001 else "message_rejected"))
        except (httpx.TimeoutException,httpx.NetworkError):return finish("retryable",self._feishu_diagnostic("token",reason="network_unavailable"))
        except (ValueError,httpx.HTTPError):return finish("failed",self._feishu_diagnostic("response",reason="message_rejected"))


def render_batches(title: str, jobs: list[dict], *, new_since: str, prior_ids: set[str] | None, warning: str = "", partial: bool = False) -> list[str]:
    from .job_catalog import instant
    prefix = f"OpenCareer · {title}\n{'已评估范围内' if partial else ''}匹配 {len(jobs)} 个岗位。\n"
    if warning:
        prefix += warning + "\n"
    prefix = prefix.encode()[:600].decode("utf-8", errors="ignore") + "\n"
    if not jobs:
        return [prefix + "本次没有匹配岗位。"]
    parts, current, delivered = [], prefix, 0
    for job in jobs:
        if len(parts) >= 9 or delivered >= 100:
            break
        recent = lambda field: bool(job.get(field)) and instant(job[field]) >= instant(new_since)
        changes = [(instant(job[field]), -rank, label) for rank, (field, label) in enumerate((("reopened_at", "【重新开放】"), ("new_at", "【新增】"), ("updated_at", "【更新】"), ("backfilled_at", "【历史补录】"))) if recent(field)]
        marker = max(changes)[2] if changes else "【新匹配】" if prior_ids is not None and job["id"] not in prior_ids else ""
        title_text = re.sub(r"[\r\n]", " ", str(job["title"])).encode()[:180].decode("utf-8", errors="ignore")
        from .job_catalog import TZ
        confirmed = instant(job["last_seen_at"]).astimezone(TZ).date().isoformat() if job.get("last_seen_at") else "未知"
        url = job["source_url"] if len(job["source_url"].encode()) <= 400 else "官网链接过长，完整地址见本机运行记录。"
        company = job["company"]["name"].encode()[:90].decode("utf-8", errors="ignore")
        locations = "、".join(job["locations"]).encode()[:90].decode("utf-8", errors="ignore")
        entry = f"\n{marker}{company} · {title_text} · {locations}\n最近确认：{confirmed}\n{url}\n"
        # WeCom's text content limit is byte based, not character based.
        if len((current + entry).encode()) > 1600:
            parts.append(current)
            current = prefix
        current += entry
        delivered += 1
    parts.append(current)
    if delivered < len(jobs):
        parts.append(f"OpenCareer · 匹配共 {len(jobs)} 项，本轮发送 {delivered} 项，尚有 {len(jobs)-delivered} 项未发送。完整结果保存在本机岗位订阅运行记录中。")
    return parts
