from __future__ import annotations

from pathlib import Path

import pytest

from logos.utils.yaml_safe import YAMLSafetyError, safe_load, safe_load_path


def test_safe_load_parses_simple_mapping() -> None:
    payload = "name: logos"
    data = safe_load(payload)
    assert data == {"name": "logos"}


def test_safe_load_rejects_object_apply() -> None:
    malicious = "!!python/object/apply:os.system ['echo unsafe']"
    with pytest.raises(YAMLSafetyError):
        safe_load(malicious)


def test_safe_load_path_wraps_errors(tmp_path: Path) -> None:
    file_path = tmp_path / "config.yaml"
    file_path.write_text(
        "!!python/object/apply:os.system ['echo hi']", encoding="utf-8"
    )
    with pytest.raises(YAMLSafetyError) as exc:
        safe_load_path(file_path)
    assert str(file_path) in str(exc.value)
    clean_path = tmp_path / "simple.yaml"
    clean_path.write_text("answer: 42", encoding="utf-8")
    result = safe_load_path(clean_path)
    assert result == {"answer": 42}
