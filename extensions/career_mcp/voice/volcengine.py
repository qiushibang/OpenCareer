"""Volcengine ASR/TTS adapter with injectable transports."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import uuid
import wave
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from coworker.secrets import SecretStore

from .base import VoiceProviderError
from .volcengine_protocol import (
    AUDIO_CHUNK_BYTES,
    VolcengineProtocolError,
    build_audio_request,
    build_full_request,
    parse_server_response,
)

ASR_URL = (
    "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
)
TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


@dataclass(frozen=True)
class VolcengineVoiceConfig:
    api_key: str
    app_id: str
    access_token: str
    asr_resource_id: str
    tts_resource_id: str
    speaker: str

    def headers(self, resource_id: str, *, tts: bool) -> dict[str, str]:
        headers = {"X-Api-Resource-Id": resource_id}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key
        else:
            headers[
                "X-Api-App-Id" if tts else "X-Api-App-Key"
            ] = self.app_id
            headers["X-Api-Access-Key"] = self.access_token
        return headers


def resolve_volcengine_config(
    secrets: SecretStore | None = None,
) -> VolcengineVoiceConfig | None:
    profile = (secrets or SecretStore()).get("voice:volcengine") or {}

    def value(env_name: str, profile_name: str) -> str:
        return str(
            os.environ.get(env_name)
            or profile.get(profile_name)
            or ""
        ).strip()

    config = VolcengineVoiceConfig(
        api_key=value("VOLCENGINE_SPEECH_API_KEY", "api_key"),
        app_id=value("VOLCENGINE_SPEECH_APP_ID", "app_id"),
        access_token=value(
            "VOLCENGINE_SPEECH_ACCESS_TOKEN",
            "access_token",
        ),
        asr_resource_id=value(
            "VOLCENGINE_ASR_RESOURCE_ID",
            "asr_resource_id",
        ),
        tts_resource_id=value(
            "VOLCENGINE_TTS_RESOURCE_ID",
            "tts_resource_id",
        ),
        speaker=value("VOLCENGINE_TTS_SPEAKER", "speaker"),
    )
    has_auth = bool(config.api_key) or bool(
        config.app_id and config.access_token
    )
    if not (
        has_auth
        and config.asr_resource_id
        and config.tts_resource_id
        and config.speaker
    ):
        return None
    return config


def _default_websocket_connect(
    url: str,
    headers: dict[str, str],
):
    return websockets.connect(
        url,
        additional_headers=headers,
        open_timeout=15,
        close_timeout=5,
    )


async def _default_http_lines(
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    timeout = httpx.Timeout(30, connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            url,
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                raise VoiceProviderError("TTS_FAILED")
            async for line in response.aiter_lines():
                if line:
                    yield line


class VolcengineVoiceProvider:
    def __init__(
        self,
        config: VolcengineVoiceConfig,
        *,
        websocket_connect: Callable = _default_websocket_connect,
        http_lines: Callable = _default_http_lines,
        timeout_seconds: float = 30,
    ) -> None:
        self._config = config
        self._websocket_connect = websocket_connect
        self._http_lines = http_lines
        self._timeout = timeout_seconds

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh-CN",
    ) -> str:
        try:
            pcm = _wav_pcm(audio)
            chunks = [
                pcm[index : index + AUDIO_CHUNK_BYTES]
                for index in range(0, len(pcm), AUDIO_CHUNK_BYTES)
            ]
            if not chunks:
                raise VoiceProviderError("ASR_FAILED")
            headers = self._config.headers(
                self._config.asr_resource_id,
                tts=False,
            )
            headers["X-Api-Connect-Id"] = str(uuid.uuid4())
            request = {
                "user": {"uid": str(uuid.uuid4())},
                "audio": {
                    "format": "pcm",
                    "codec": "raw",
                    "rate": 16_000,
                    "bits": 16,
                    "channel": 1,
                    "language": language,
                },
                "request": {
                    "model_name": "bigmodel",
                    "enable_itn": True,
                    "enable_punc": True,
                    "result_type": "full",
                },
            }
            latest = ""
            async with self._websocket_connect(
                ASR_URL,
                headers,
            ) as socket:
                await socket.send(build_full_request(request, sequence=1))
                latest = _response_text(
                    await asyncio.wait_for(
                        socket.recv(),
                        timeout=self._timeout,
                    )
                )
                for index, chunk in enumerate(chunks, start=2):
                    await socket.send(
                        build_audio_request(
                            chunk,
                            sequence=index,
                            final=index == len(chunks) + 1,
                        )
                    )
                    text = _response_text(
                        await asyncio.wait_for(
                            socket.recv(),
                            timeout=self._timeout,
                        )
                    )
                    if text:
                        latest = text
            if not latest.strip():
                raise VoiceProviderError("ASR_FAILED")
            return latest.strip()
        except VoiceProviderError:
            raise
        except (
            asyncio.TimeoutError,
            OSError,
            ValueError,
            VolcengineProtocolError,
        ) as exc:
            raise VoiceProviderError("ASR_FAILED") from exc
        except Exception as exc:
            raise VoiceProviderError("ASR_FAILED") from exc

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "interviewer",
    ) -> bytes:
        del voice
        headers = self._config.headers(
            self._config.tts_resource_id,
            tts=True,
        )
        headers["X-Api-Request-Id"] = str(uuid.uuid4())
        payload = {
            "user": {"uid": str(uuid.uuid4())},
            "req_params": {
                "text": text,
                "speaker": self._config.speaker,
                "audio_params": {
                    "format": "mp3",
                    "sample_rate": 24_000,
                },
            },
        }
        output = bytearray()
        completed = False
        try:
            async for line in self._http_lines(
                TTS_URL,
                headers,
                payload,
            ):
                item = json.loads(line)
                code = int(item.get("code", -1))
                if code == 20_000_000:
                    completed = True
                    continue
                if code != 0:
                    raise VoiceProviderError("TTS_FAILED")
                data = item.get("data")
                if isinstance(data, str) and data:
                    output.extend(base64.b64decode(data, validate=True))
            if not completed or not output:
                raise VoiceProviderError("TTS_FAILED")
            return bytes(output)
        except VoiceProviderError:
            raise
        except (
            asyncio.TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            raise VoiceProviderError("TTS_FAILED") from exc
        except Exception as exc:
            raise VoiceProviderError("TTS_FAILED") from exc


def _wav_pcm(audio: bytes) -> bytes:
    with wave.open(io.BytesIO(audio), "rb") as reader:
        return reader.readframes(reader.getnframes())


def _response_text(data: bytes | str) -> str:
    if not isinstance(data, bytes):
        raise VolcengineProtocolError("response must be binary")
    payload = parse_server_response(data)["payload"]
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result")
    if isinstance(result, dict):
        return str(result.get("text") or "")
    if isinstance(result, list):
        for item in reversed(result):
            if isinstance(item, dict) and item.get("text"):
                return str(item["text"])
    return ""
