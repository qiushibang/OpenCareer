from __future__ import annotations

import base64
import gzip
import io
import json
import wave

import pytest

from coworker.secrets import SecretStore
from extensions.career_mcp.services.interview_voice import (
    InterviewVoiceService,
    InterviewVoiceServiceError,
)
from extensions.career_mcp.voice.base import VoiceProviderError
from extensions.career_mcp.voice.volcengine import (
    VolcengineVoiceConfig,
    VolcengineVoiceProvider,
    resolve_volcengine_config,
)
from extensions.career_mcp.voice.volcengine_protocol import (
    AUDIO_CHUNK_BYTES,
    build_audio_request,
    build_full_request,
    frame_header,
    parse_server_response,
)


def _wav(
    *,
    seconds: int = 1,
    sample_rate: int = 16_000,
    channels: int = 1,
    bits: int = 16,
) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(bits // 8)
        writer.setframerate(sample_rate)
        writer.writeframes(
            b"\x00" * (seconds * sample_rate * channels * (bits // 8))
        )
    return output.getvalue()


def _server_frame(payload: dict, sequence: int = 1) -> bytes:
    compressed = gzip.compress(
        json.dumps(payload, ensure_ascii=False).encode()
    )
    return (
        frame_header(
            message_type=9,
            flags=1,
            serialization=1,
            compression=1,
        )
        + sequence.to_bytes(4, "big", signed=True)
        + len(compressed).to_bytes(4, "big")
        + compressed
    )


class FakeWebSocket:
    def __init__(self, responses: list[bytes]) -> None:
        self.responses = list(responses)
        self.sent: list[bytes] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def send(self, value: bytes) -> None:
        self.sent.append(value)

    async def recv(self) -> bytes:
        return self.responses.pop(0)


def _config(**overrides) -> VolcengineVoiceConfig:
    values = {
        "api_key": "speech-secret-key",
        "app_id": "",
        "access_token": "",
        "asr_resource_id": "volc.seedasr.sauc.duration",
        "tts_resource_id": "seed-tts-2.0",
        "speaker": "zh_male_ruyayichen_uranus_bigtts",
    }
    values.update(overrides)
    return VolcengineVoiceConfig(**values)


def test_protocol_frames_use_big_endian_sequence_and_gzip():
    payload = {"audio": {"format": "pcm", "rate": 16_000}}

    full = build_full_request(payload, sequence=1)
    audio = build_audio_request(b"pcm", sequence=2, final=False)
    final = build_audio_request(b"last", sequence=3, final=True)

    assert full[:4] == bytes([0x11, 0x11, 0x11, 0x00])
    assert int.from_bytes(full[4:8], "big", signed=True) == 1
    size = int.from_bytes(full[8:12], "big")
    assert json.loads(gzip.decompress(full[12 : 12 + size])) == payload
    assert audio[:4] == bytes([0x11, 0x21, 0x00, 0x00])
    assert int.from_bytes(audio[4:8], "big", signed=True) == 2
    assert final[:4] == bytes([0x11, 0x23, 0x00, 0x00])
    assert int.from_bytes(final[4:8], "big", signed=True) == -3


def test_protocol_parses_gzip_server_response():
    parsed = parse_server_response(
        _server_frame({"result": {"text": "你好"}})
    )

    assert parsed["sequence"] == 1
    assert parsed["payload"]["result"]["text"] == "你好"


@pytest.mark.asyncio
async def test_asr_sends_200ms_pcm_packets_and_new_auth_headers():
    pcm_bytes = AUDIO_CHUNK_BYTES * 2
    audio = _wav(seconds=1)[:44] + b"\x01" * pcm_bytes
    socket = FakeWebSocket(
        [
            _server_frame({"result": {"text": ""}}, 1),
            _server_frame({"result": {"text": "你"}}, 2),
            _server_frame({"result": {"text": "你好"}}, 3),
        ]
    )
    calls: list[tuple[str, dict[str, str]]] = []

    def connect(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        return socket

    provider = VolcengineVoiceProvider(
        _config(),
        websocket_connect=connect,
    )
    transcript = await provider.transcribe(audio)

    assert transcript == "你好"
    assert calls[0][0].endswith("/api/v3/sauc/bigmodel_nostream")
    assert calls[0][1]["X-Api-Key"] == "speech-secret-key"
    assert calls[0][1]["X-Api-Resource-Id"] == (
        "volc.seedasr.sauc.duration"
    )
    request_size = int.from_bytes(socket.sent[0][8:12], "big")
    request = json.loads(
        gzip.decompress(socket.sent[0][12 : 12 + request_size])
    )
    assert request["audio"] == {
        "format": "pcm",
        "codec": "raw",
        "rate": 16_000,
        "bits": 16,
        "channel": 1,
        "language": "zh-CN",
    }
    assert request["request"]["model_name"] == "bigmodel"
    assert len(socket.sent) == 3
    assert int.from_bytes(socket.sent[-1][4:8], "big", signed=True) < 0


@pytest.mark.asyncio
async def test_tts_uses_legacy_headers_and_concatenates_audio_chunks():
    calls: list[tuple[str, dict, dict]] = []

    async def lines(url: str, headers: dict, payload: dict):
        calls.append((url, headers, payload))
        yield json.dumps(
            {"code": 0, "data": base64.b64encode(b"one").decode()}
        )
        yield json.dumps({"code": 0, "data": None, "sentence": {}})
        yield json.dumps(
            {"code": 0, "data": base64.b64encode(b"two").decode()}
        )
        yield json.dumps({"code": 20_000_000, "message": "ok"})

    provider = VolcengineVoiceProvider(
        _config(
            api_key="",
            app_id="app-id",
            access_token="access-secret",
        ),
        http_lines=lines,
    )
    audio = await provider.synthesize("请介绍你的项目经历。")

    assert audio == b"onetwo"
    url, headers, payload = calls[0]
    assert url.endswith("/api/v3/tts/unidirectional")
    assert headers["X-Api-App-Id"] == "app-id"
    assert headers["X-Api-Access-Key"] == "access-secret"
    assert headers["X-Api-Resource-Id"] == "seed-tts-2.0"
    assert payload["req_params"]["speaker"] == (
        "zh_male_ruyayichen_uranus_bigtts"
    )
    assert payload["req_params"]["audio_params"] == {
        "format": "mp3",
        "sample_rate": 24_000,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "expected_code"),
    [("asr", "ASR_FAILED"), ("tts", "TTS_FAILED")],
)
async def test_provider_failures_are_stable_and_hide_secrets(
    operation,
    expected_code,
):
    async def broken_lines(*_args):
        yield "{provider-body: speech-secret-key"

    class BrokenSocket(FakeWebSocket):
        async def recv(self):
            raise TimeoutError("speech-secret-key provider body")

    provider = VolcengineVoiceProvider(
        _config(),
        websocket_connect=lambda *_args: BrokenSocket([]),
        http_lines=broken_lines,
    )

    with pytest.raises(VoiceProviderError) as raised:
        if operation == "asr":
            await provider.transcribe(_wav())
        else:
            await provider.synthesize("请介绍你的项目经历。")

    assert raised.value.code == expected_code
    assert "speech-secret-key" not in str(raised.value)
    assert "provider-body" not in str(raised.value)


def test_credentials_resolve_environment_over_secret_store(
    tmp_path,
    monkeypatch,
):
    secrets = SecretStore(tmp_path / "secrets.json")
    secrets.put(
        "voice:volcengine",
        {
            "app_id": "stored-app",
            "access_token": "stored-token",
            "asr_resource_id": "stored-asr",
            "tts_resource_id": "stored-tts",
            "speaker": "stored-speaker",
        },
    )
    monkeypatch.setenv("VOLCENGINE_SPEECH_API_KEY", "env-key")
    monkeypatch.setenv("VOLCENGINE_ASR_RESOURCE_ID", "env-asr")
    monkeypatch.setenv("VOLCENGINE_TTS_RESOURCE_ID", "env-tts")
    monkeypatch.setenv("VOLCENGINE_TTS_SPEAKER", "env-speaker")

    config = resolve_volcengine_config(secrets)

    assert config is not None
    assert config.api_key == "env-key"
    assert config.asr_resource_id == "env-asr"
    assert config.tts_resource_id == "env-tts"
    assert config.speaker == "env-speaker"


class FakeProvider:
    def __init__(self) -> None:
        self.transcribe_calls: list[bytes] = []
        self.synthesize_calls: list[str] = []

    async def transcribe(
        self,
        audio: bytes,
        *,
        language: str = "zh-CN",
    ) -> str:
        self.transcribe_calls.append(audio)
        return "可编辑的识别文本"

    async def synthesize(
        self,
        text: str,
        *,
        voice: str = "interviewer",
    ) -> bytes:
        self.synthesize_calls.append(text)
        return b"mp3"


@pytest.mark.asyncio
async def test_voice_service_is_memory_only(monkeypatch):
    provider = FakeProvider()
    service = InterviewVoiceService(provider=provider)

    def fail_write(*_args, **_kwargs):
        raise AssertionError("voice service must not write files")

    monkeypatch.setattr("pathlib.Path.write_bytes", fail_write)
    transcript = await service.transcribe(_wav(), mime="audio/wav")
    audio = await service.synthesize("请介绍你的项目经历。")

    assert transcript == "可编辑的识别文本"
    assert audio == b"mp3"
    assert len(provider.transcribe_calls) == 1
    assert provider.synthesize_calls == ["请介绍你的项目经历。"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "audio,mime",
    [
        (b"not-wav", "audio/wav"),
        (_wav(), "audio/mp3"),
        (_wav(sample_rate=8_000), "audio/wav"),
        (_wav(channels=2), "audio/wav"),
        (_wav(bits=8), "audio/wav"),
    ],
)
async def test_voice_service_rejects_invalid_audio_before_transport(
    audio,
    mime,
):
    provider = FakeProvider()
    service = InterviewVoiceService(provider=provider)

    with pytest.raises(InterviewVoiceServiceError) as raised:
        await service.transcribe(audio, mime=mime)

    assert raised.value.code == "ASR_FAILED"
    assert provider.transcribe_calls == []


@pytest.mark.asyncio
async def test_voice_service_enforces_size_duration_and_text_bounds():
    provider = FakeProvider()
    service = InterviewVoiceService(provider=provider)

    for audio in (b"x" * (20 * 1024 * 1024 + 1), _wav(seconds=301)):
        with pytest.raises(InterviewVoiceServiceError) as raised:
            await service.transcribe(audio, mime="audio/wav")
        assert raised.value.code == "ASR_FAILED"
    for text in ("短", "问" * 201):
        with pytest.raises(InterviewVoiceServiceError) as raised:
            await service.synthesize(text)
        assert raised.value.code == "TTS_FAILED"
    assert provider.transcribe_calls == []
    assert provider.synthesize_calls == []


@pytest.mark.asyncio
async def test_voice_service_requires_credentials_before_transport(
    tmp_path,
):
    service = InterviewVoiceService(
        secrets=SecretStore(tmp_path / "secrets.json")
    )

    with pytest.raises(InterviewVoiceServiceError) as raised:
        await service.transcribe(_wav(), mime="audio/wav")

    assert raised.value.code == "VOICE_NOT_CONFIGURED"
