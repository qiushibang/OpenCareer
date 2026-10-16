"""Bounded, memory-only voice orchestration for mock interviews."""

from __future__ import annotations

import io
import wave

from coworker.secrets import SecretStore

from ..voice.base import VoiceProvider, VoiceProviderError
from ..voice.volcengine import (
    VolcengineVoiceProvider,
    resolve_volcengine_config,
)

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MAX_AUDIO_SECONDS = 300
MIN_TTS_CHARS = 5
MAX_TTS_CHARS = 200


class InterviewVoiceServiceError(ValueError):
    def __init__(self, code: str) -> None:
        message = {
            "VOICE_NOT_CONFIGURED": "尚未配置模拟面试语音服务。",
            "ASR_FAILED": "语音识别失败，请重试或输入文字回答。",
            "TTS_FAILED": "语音播放生成失败，请直接阅读文字问题。",
        }.get(code, "模拟面试语音服务失败。")
        super().__init__(message)
        self.code = code


class InterviewVoiceService:
    def __init__(
        self,
        *,
        provider: VoiceProvider | None = None,
        secrets: SecretStore | None = None,
    ) -> None:
        self._injected_provider = provider
        self._secrets = secrets

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str,
    ) -> str:
        _validate_audio(audio, mime)
        provider = self._provider()
        try:
            transcript = (
                await provider.transcribe(audio, language="zh-CN")
            ).strip()
        except VoiceProviderError as exc:
            raise InterviewVoiceServiceError("ASR_FAILED") from exc
        except Exception as exc:
            raise InterviewVoiceServiceError("ASR_FAILED") from exc
        if not transcript:
            raise InterviewVoiceServiceError("ASR_FAILED")
        return transcript

    async def synthesize(self, text: str) -> bytes:
        normalized = text.strip() if isinstance(text, str) else ""
        if not MIN_TTS_CHARS <= len(normalized) <= MAX_TTS_CHARS:
            raise InterviewVoiceServiceError("TTS_FAILED")
        provider = self._provider()
        try:
            audio = await provider.synthesize(
                normalized,
                voice="interviewer",
            )
        except VoiceProviderError as exc:
            raise InterviewVoiceServiceError("TTS_FAILED") from exc
        except Exception as exc:
            raise InterviewVoiceServiceError("TTS_FAILED") from exc
        if not isinstance(audio, bytes) or not audio:
            raise InterviewVoiceServiceError("TTS_FAILED")
        return audio

    def _provider(self) -> VoiceProvider:
        if self._injected_provider is not None:
            return self._injected_provider
        config = resolve_volcengine_config(self._secrets)
        if config is None:
            raise InterviewVoiceServiceError("VOICE_NOT_CONFIGURED")
        return VolcengineVoiceProvider(config)


def _validate_audio(audio: bytes, mime: str) -> None:
    if (
        mime != "audio/wav"
        or not isinstance(audio, bytes)
        or not audio
        or len(audio) > MAX_AUDIO_BYTES
        or audio[:4] != b"RIFF"
        or audio[8:12] != b"WAVE"
    ):
        raise InterviewVoiceServiceError("ASR_FAILED")
    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            channels = reader.getnchannels()
            bits = reader.getsampwidth() * 8
            sample_rate = reader.getframerate()
            frames = reader.getnframes()
    except (EOFError, wave.Error) as exc:
        raise InterviewVoiceServiceError("ASR_FAILED") from exc
    if (
        channels != 1
        or bits != 16
        or sample_rate != 16_000
        or frames <= 0
        or frames / sample_rate > MAX_AUDIO_SECONDS
    ):
        raise InterviewVoiceServiceError("ASR_FAILED")
