"""Volcengine big-model ASR binary framing."""

from __future__ import annotations

import gzip
import json
from typing import Any

AUDIO_CHUNK_BYTES = 16_000 * 2 // 5  # 200 ms, mono PCM16.


class VolcengineProtocolError(ValueError):
    pass


def frame_header(
    *,
    message_type: int,
    flags: int,
    serialization: int,
    compression: int,
) -> bytes:
    values = (message_type, flags, serialization, compression)
    if any(value < 0 or value > 0xF for value in values):
        raise VolcengineProtocolError("invalid header field")
    return bytes(
        [
            (1 << 4) | 1,
            (message_type << 4) | flags,
            (serialization << 4) | compression,
            0,
        ]
    )


def build_full_request(payload: dict[str, Any], *, sequence: int) -> bytes:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    compressed = gzip.compress(encoded)
    return (
        frame_header(
            message_type=1,
            flags=1,
            serialization=1,
            compression=1,
        )
        + sequence.to_bytes(4, "big", signed=True)
        + len(compressed).to_bytes(4, "big")
        + compressed
    )


def build_audio_request(
    payload: bytes,
    *,
    sequence: int,
    final: bool,
) -> bytes:
    wire_sequence = -abs(sequence) if final else sequence
    return (
        frame_header(
            message_type=2,
            flags=3 if final else 1,
            serialization=0,
            compression=0,
        )
        + wire_sequence.to_bytes(4, "big", signed=True)
        + len(payload).to_bytes(4, "big")
        + payload
    )


def parse_server_response(data: bytes) -> dict[str, Any]:
    if len(data) < 8:
        raise VolcengineProtocolError("response is too short")
    header_size = (data[0] & 0xF) * 4
    if header_size < 4 or len(data) < header_size + 4:
        raise VolcengineProtocolError("invalid response header")
    message_type = data[1] >> 4
    flags = data[1] & 0xF
    serialization = data[2] >> 4
    compression = data[2] & 0xF
    offset = header_size
    sequence: int | None = None
    if flags & 1:
        if len(data) < offset + 4:
            raise VolcengineProtocolError("missing response sequence")
        sequence = int.from_bytes(
            data[offset : offset + 4],
            "big",
            signed=True,
        )
        offset += 4
    error_code: int | None = None
    if message_type == 0xF:
        if len(data) < offset + 8:
            raise VolcengineProtocolError("invalid error response")
        error_code = int.from_bytes(data[offset : offset + 4], "big")
        offset += 4
    if len(data) < offset + 4:
        raise VolcengineProtocolError("missing response payload size")
    size = int.from_bytes(data[offset : offset + 4], "big")
    offset += 4
    payload_bytes = data[offset : offset + size]
    if len(payload_bytes) != size:
        raise VolcengineProtocolError("truncated response payload")
    if compression == 1:
        try:
            payload_bytes = gzip.decompress(payload_bytes)
        except (OSError, EOFError) as exc:
            raise VolcengineProtocolError(
                "invalid compressed response"
            ) from exc
    if serialization == 1:
        try:
            payload: Any = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VolcengineProtocolError(
                "invalid JSON response"
            ) from exc
    else:
        payload = payload_bytes
    if message_type == 0xF:
        raise VolcengineProtocolError(
            f"provider error {error_code or 0}"
        )
    if message_type != 9:
        raise VolcengineProtocolError("unexpected response type")
    return {"sequence": sequence, "payload": payload}
