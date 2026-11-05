"""Local outbound-only pairing via Feishu's official PersonalAgent registration.

Protocol verified against @larksuite/openclaw-lark-tools 1.0.47 (MIT),
utils/feishu-auth.js. Independent implementation; no OpenClaw installation.
"""
from __future__ import annotations

import base64
import io
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

import httpx
import qrcode
import qrcode.image.svg

from .job_notifications import _private_transport

URL = "https://accounts.feishu.cn/oauth/v1/app/registration"
_PENDING: dict[tuple[str, str], dict] = {}
_LOCK = threading.RLock()


class FeishuPairing:
    def __init__(self, subscriptions, *, transport=None, clock=time.time):
        self.subscriptions = subscriptions
        self.scope = str(subscriptions.config.data_dir.resolve())
        self.transport, self.clock = transport, clock

    def _request(self, body: dict) -> dict:
        try:
            with _private_transport(), httpx.Client(transport=self.transport, timeout=10, follow_redirects=False, trust_env=False) as client:
                response = client.post(URL, data=body)
            if len(response.content) > 64000 or response.status_code not in {200, 400}:
                raise ValueError()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
            return data
        except (httpx.HTTPError, ValueError):
            raise ValueError("飞书扫码服务暂时不可用，请稍后重试。") from None

    def begin(self) -> dict:
        with _LOCK:
            for key, value in list(_PENDING.items()):
                if value["expires_at"] < self.clock():
                    del _PENDING[key]
            if sum(key[0] == self.scope for key in _PENDING) >= 5:
                raise ValueError("正在进行的扫码较多，请取消旧二维码后重试。")
            init = self._request({"action": "init"})
            if "client_secret" not in init.get("supported_auth_methods", []):
                raise ValueError("当前飞书环境未开放扫码创建，请使用下方群机器人方式。")
            data = self._request({"action":"begin", "archetype":"PersonalAgent", "auth_method":"client_secret", "request_user_info":"open_id"})
            code, uri = data.get("device_code"), data.get("verification_uri_complete")
            if not isinstance(code, str) or not 1 <= len(code) <= 2000 or not isinstance(uri, str) or len(uri) > 4000:
                raise ValueError("飞书未返回有效二维码，请重试。")
            url = urlsplit(uri)
            if url.scheme != "https" or url.hostname not in {"accounts.feishu.cn", "open.feishu.cn", "applink.feishu.cn"} or url.username or url.password or url.port not in {None,443}:
                raise ValueError("飞书返回的授权地址不受支持，请使用国内飞书账号。")
            interval = min(30,max(5,int(data.get("interval") or 5)))
            expiry = min(900,max(30,int(data.get("expire_in") or data.get("expires_in") or 600)))
            sid = secrets.token_hex(24)
            _PENDING[self.scope,sid] = {"device_code":code,"expires_at":self.clock()+expiry,"interval":interval,"next_poll":self.clock()+interval,"state":"pending"}
            output = io.BytesIO()
            qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage,box_size=8,border=4).save(output)
            return {"session_id":sid,"verification_url":uri,"qr_image":"data:image/svg+xml;base64,"+base64.b64encode(output.getvalue()).decode(),"expires_in":expiry,"interval":interval,"state":"pending"}

    def poll(self, sid: str) -> dict:
        if not isinstance(sid,str) or not re.fullmatch(r"[a-f0-9]{48}",sid):
            raise ValueError("扫码会话无效，请重新生成二维码。")
        with _LOCK:
            session = _PENDING.get((self.scope,sid))
            if not session:
                return {"state":"expired"}
            if session["expires_at"] <= self.clock():
                del _PENDING[self.scope,sid]
                return {"state":"expired"}
            if session["state"] == "connected":
                return {"state":"connected","channel":session["channel"]}
            if self.clock() < session["next_poll"]:
                return {"state":"pending","interval":session["interval"]}
            session["next_poll"] = self.clock()+session["interval"]
            device_code = session["device_code"]
        # Cancellation stays responsive while an upstream poll is in flight.
        result = self._request({"action":"poll","device_code":device_code})
        with _LOCK:
            if _PENDING.get((self.scope,sid)) is not session:
                return {"state":"expired"}
            if session["expires_at"] <= self.clock():
                del _PENDING[self.scope,sid]
                return {"state":"expired"}
            if result.get("user_info",{}).get("tenant_brand") == "lark":
                del _PENDING[self.scope,sid]
                raise ValueError("本轮先支持国内飞书扫码，国际Lark请使用群机器人配置。")
            if result.get("client_id") and result.get("client_secret"):
                channel = self.subscriptions.save_feishu_app(result["client_id"],result["client_secret"],result.get("user_info",{}).get("open_id"))
                session.clear()
                session.update(state="connected",channel=channel,expires_at=self.clock()+120)
                return {"state":"connected","channel":channel}
            error = result.get("error")
            if error == "slow_down":
                session["interval"] = min(60,session["interval"]+5)
                session["next_poll"] = self.clock()+session["interval"]
            elif error in {"access_denied","authorization_declined","expired_token"}:
                del _PENDING[self.scope,sid]
                return {"state":"cancelled" if error != "expired_token" else "expired"}
            elif error not in {None,"authorization_pending","slow_down"}:
                del _PENDING[self.scope,sid]
                raise ValueError("飞书授权未完成，请重新扫码；请核对平台显示的权限和管理员要求。")
            return {"state":"pending","interval":session["interval"]}

    def cancel(self,sid: str) -> dict:
        with _LOCK:
            _PENDING.pop((self.scope,sid),None)
        return {"state":"cancelled"}
