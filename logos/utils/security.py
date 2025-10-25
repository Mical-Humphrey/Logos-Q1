from __future__ import annotations

import logging
import re
from typing import Any, Mapping

MASK_TOKEN = "<redacted>"
SENSITIVE_KEY_PATTERN = re.compile(r"(?i)(token|secret|key|pass|private|signing)")
_KEY_VALUE_PATTERN = re.compile(
    r"(?i)([\w.-]*(?:token|secret|key|pass|private|signing)[\w.-]*)(\s*[:=]\s*)([^\s,;]+)"
)
_JSON_QUOTED_PATTERN = re.compile(
    r"(?i)(\"|')([\w.-]*(?:token|secret|key|pass|private|signing)[\w.-]*)(\"|')\s*:\s*(\"|')([^\"']*)(\"|')"
)
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]+")
_FORMULA_PREFIXES = ("=", "+", "-", "@")

__all__ = [
    "RedactingFilter",
    "redact_text",
    "redact_mapping",
    "scrub_artifact",
    "csv_cell_sanitize",
    "MASK_TOKEN",
]


def _mask_value(match: re.Match[str]) -> str:
    key = match.group(1)
    delim = match.group(2)
    return f"{key}{delim}{MASK_TOKEN}"


def _mask_json_value(match: re.Match[str]) -> str:
    quote_l = match.group(1)
    key = match.group(2)
    quote_r = match.group(3)
    value_quote_l = match.group(4)
    value_quote_r = match.group(6)
    return f"{quote_l}{key}{quote_r}: {value_quote_l}{MASK_TOKEN}{value_quote_r}"


def redact_text(message: str) -> str:
    """Return *message* with sensitive key/value pairs replaced."""

    redacted = _KEY_VALUE_PATTERN.sub(_mask_value, message)
    redacted = _JSON_QUOTED_PATTERN.sub(_mask_json_value, redacted)

    def _mask_bearer(match: re.Match[str]) -> str:
        return "Bearer " + MASK_TOKEN

    redacted = _BEARER_PATTERN.sub(_mask_bearer, redacted)
    return redacted


class RedactingFilter(logging.Filter):
    """Logging filter that redacts secret-looking keys before emission."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - thin shim
        message = record.getMessage()
        redacted = redact_text(message)
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def _is_sensitive_key(key: Any) -> bool:
    return isinstance(key, str) and bool(SENSITIVE_KEY_PATTERN.search(key))


def redact_mapping(payload: Any) -> Any:
    """Recursively redact values whose keys imply sensitive data."""

    if isinstance(payload, Mapping):
        result: dict[Any, Any] = {}
        for key, value in payload.items():
            if _is_sensitive_key(key):
                result[key] = MASK_TOKEN if value not in (None, "") else value
            else:
                result[key] = redact_mapping(value)
        return result
    if isinstance(payload, (list, tuple)):
        items = [redact_mapping(item) for item in payload]
        return type(payload)(items)
    if isinstance(payload, set):
        return {redact_mapping(item) for item in payload}
    return payload


def scrub_artifact(payload: Any) -> Any:
    """Return a deep-redacted copy suitable for persistence."""

    return redact_mapping(payload)


def csv_cell_sanitize(value: Any) -> Any:
    """Neutralise formula injections and normalise newlines for CSV output."""

    if isinstance(value, str):
        text = value.replace("\r\n", "\n").replace("\r", "\n")
        if text.startswith(_FORMULA_PREFIXES):
            return "'" + text
        return text
    return value