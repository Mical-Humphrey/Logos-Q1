from __future__ import annotations

from pathlib import Path

import pytest

from core.io.chunked_reader import (
    read_csv_chunked,
    ReaderLimitError,
)


def _make_csv(path: Path, rows: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("a,b,c\n")
        for i in range(rows):
            fh.write(f"{i},{i*2},val{i}\n")


def test_row_limit(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    _make_csv(p, 10)
    gen = read_csv_chunked(p, max_rows=5)
    with pytest.raises(ReaderLimitError):
        list(gen)


def test_byte_limit(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    _make_csv(p, 10)
    # tiny byte limit
    gen = read_csv_chunked(p, max_bytes=10)
    with pytest.raises(ReaderLimitError):
        list(gen)


def test_schema_validation(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    _make_csv(p, 3)
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    # since csv values are strings, this should pass
    gen = read_csv_chunked(p, schema=schema)
    rows = list(gen)
    assert len(rows) == 3
    assert gen.metadata.rows == 3


def test_sample_metadata(tmp_path: Path) -> None:
    p = tmp_path / "data.csv"
    _make_csv(p, 2)
    gen = read_csv_chunked(p, sample_lines=2)
    rows = list(gen)
    assert len(rows) == 2
    assert gen.metadata.sample.lines
    assert gen.metadata.sample.sha256
