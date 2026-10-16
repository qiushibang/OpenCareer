"""Deterministic detection of private values in Career free text."""

from __future__ import annotations

import re
import unicodedata

_PRIVATE_VALUE_PATTERNS = (
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(
        r"/Users/|(?:^|[\s`'\"])[A-Za-z]:[\\/]",
        re.MULTILINE,
    ),
    re.compile(r"(?:private[_ -]?path|upload[_ -]?token)", re.IGNORECASE),
    re.compile(r"(?<!\d)(?:\d{17}[\dXx]|\d{15})(?!\d)"),
    re.compile(
        r"(?:微信(?:号|ID)?|wechat(?:\s*id)?|vx|v信)"
        r"\s*(?:[:：=]|是|为)?\s*[A-Za-z][A-Za-z0-9_-]{3,}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:身份证(?:号)?|id\s*card)"
        r"\s*[:：]?\s*[0-9Xx][0-9Xx -]{13,24}",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:出生日期|出生年月|出生于|生于|生日|birth\s*date)"
        r"\s*(?:[:：=]|是|为)?\s*"
        r"\d{4}(?:[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"年\d{1,2}月\d{1,2}日?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\d{4}(?:[-/.]\d{1,2}[-/.]\d{1,2}|"
        r"年\d{1,2}月\d{1,2}日?)\s*(?:出生|生)",
        re.IGNORECASE,
    ),
)


def contains_sensitive_value(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value)
    compact_identifier = re.sub(
        r"(?<=\d)[ \t./-]+(?=[\dXx])",
        "",
        normalized,
    )
    return any(
        pattern.search(candidate)
        for pattern in _PRIVATE_VALUE_PATTERNS
        for candidate in (normalized, compact_identifier)
    )
