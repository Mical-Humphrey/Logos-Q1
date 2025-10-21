from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.contracts import (
    SIZE_LIMIT_BYTES,
    StrategiesIndexValidationError,
    build_strategies_index,
    generate_strategies_index,
    validate_strategies_index,
)
from logos.tools.generate_strategies_index import main as generate_index_cli


def test_build_strategies_index_sorted_and_validates() -> None:
    strategies = {
        "bravo": lambda df: df,
        "alpha": lambda df: df,
        "charlie": lambda df: df,
    }

    payload = build_strategies_index(strategies=strategies)

    validate_strategies_index(payload)
    ids = [entry["strategy_id"] for entry in payload["strategies"]]
    assert ids == sorted(ids)
    assert payload["version"] == "v1"
    assert payload["ext"] == {}
    assert payload["generated_at"].endswith("Z")


def test_generate_strategies_index_writes_file_and_is_under_limit(tmp_path) -> None:
    out_path = tmp_path / "contracts" / "index.json"

    payload = generate_strategies_index(out_path)

    validate_strategies_index(payload)
    data = json.loads(out_path.read_text("utf-8"))

    assert data == payload
    assert len(json.dumps(data).encode("utf-8")) <= SIZE_LIMIT_BYTES


def test_generate_strategies_index_respects_size_limit(tmp_path) -> None:
    out_path = tmp_path / "index.json"

    with pytest.raises(ValueError) as excinfo:
        generate_strategies_index(out_path, size_limit_bytes=64)

    assert "strategies index exceeds limit" in str(excinfo.value)
    assert not out_path.exists()


def test_build_strategies_index_custom_generated_at() -> None:
    frozen = datetime(2024, 1, 1, tzinfo=timezone.utc)
    payload = build_strategies_index(generated_at=frozen)
    assert payload["generated_at"] == "2024-01-01T00:00:00Z"


def test_validate_strategies_index_disallows_duplicate_ids() -> None:
    payload = build_strategies_index(strategies={"alpha": lambda df: df})
    duplicate_entry = payload["strategies"][0].copy()
    payload["strategies"].append(duplicate_entry)

    with pytest.raises(StrategiesIndexValidationError) as excinfo:
        validate_strategies_index(payload)

        assert "strategies" in str(excinfo.value)


def test_validate_strategies_index_allows_ext_expansion() -> None:
    payload = build_strategies_index(strategies={"alpha": lambda df: df})
    payload["strategies"][0]["ext"]["notes"] = "demo"
    payload["ext"]["owner"] = "agent1"

    validate_strategies_index(payload)


def test_generate_strategies_index_cli_success(tmp_path) -> None:
    out_path = tmp_path / "index.json"

    exit_code = generate_index_cli(["--out", str(out_path)])

    assert exit_code == 0
    document = json.loads(out_path.read_text("utf-8"))
    validate_strategies_index(document)


def test_generate_strategies_index_cli_size_guard(tmp_path, capsys) -> None:
    out_path = tmp_path / "index.json"

    exit_code = generate_index_cli(
        [
            "--out",
            str(out_path),
            "--size-limit-bytes",
            "128",
        ]
    )

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "exceeds limit" in captured.err
    assert not out_path.exists()
