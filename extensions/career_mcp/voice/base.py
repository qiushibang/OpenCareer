"""Provider-neutral voice contracts for mock interviews."""

from __future__ import annotations

from typing import Protocol


class VoiceProviderError(ValueError):
    def __init__(self, code: str) -> None:
        message = {
            "ASR_FAILED": "语音识别失败。",
            "TTS_FAILED": "语音合成失败。",
        }.get(code, "语音服务失败。")
        super().__init__(message)
        self.code = code


class VoiceProvider(Protocol):
    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh-CN",
    ) -> str: ...

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "interviewer",
    ) -> bytes: ...
