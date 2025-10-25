from __future__ import annotations

import io
import logging

from logos.utils.security import (
    MASK_TOKEN,
    RedactingFilter,
    csv_cell_sanitize,
    redact_mapping,
    redact_text,
)


def test_redact_text_masks_common_keys() -> None:
    message = "alpaca_secret_key=abc123, API_TOKEN=xyz"
    redacted = redact_text(message)
    assert MASK_TOKEN in redacted
    assert "abc123" not in redacted
    assert "xyz" not in redacted


def test_redact_mapping_masks_nested_structures() -> None:
    payload = {
        "token": "abc",
        "nested": {"ApiSecret": "value", "ok": "safe"},
        "list": [
            {"signing_key": "123"},
            "nope",
        ],
    }
    redacted = redact_mapping(payload)
    assert redacted["token"] == MASK_TOKEN
    assert redacted["nested"]["ApiSecret"] == MASK_TOKEN
    assert redacted["nested"]["ok"] == "safe"
    assert redacted["list"][0]["signing_key"] == MASK_TOKEN
    assert redacted["list"][1] == "nope"


def test_csv_cell_sanitize_neutralizes_formulas() -> None:
    assert csv_cell_sanitize("=SUM(A1:A3)") == "'" + "=SUM(A1:A3)"
    assert csv_cell_sanitize("+2") == "'+2"
    assert csv_cell_sanitize("@cmd") == "'@cmd"
    assert csv_cell_sanitize("safe") == "safe"
    assert csv_cell_sanitize("line\r\nbreak") == "line\nbreak"


def test_redacting_filter_masks_log_output() -> None:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RedactingFilter())
    logger = logging.getLogger("test_redaction_logger")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        logger.info("api_secret=top-secret")
        contents = stream.getvalue()
    finally:
        logger.removeHandler(handler)
    assert MASK_TOKEN in contents
    assert "top-secret" not in contents
