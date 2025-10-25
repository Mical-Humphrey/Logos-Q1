from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from logos.data import cli


def _write_fixture(path: Path) -> None:
    idx = pd.date_range("2024-01-01", periods=3, freq="1D")
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.0, 103.0],
            "Low": [99.0, 100.0, 101.0],
            "Close": [100.5, 101.5, 102.5],
            "Adj Close": [100.5, 101.5, 102.5],
            "Volume": [1_000, 1_100, 1_050],
        },
        index=idx,
    )
    frame.to_csv(path, index_label="Date")


def _patch_data_dirs(monkeypatch, raw: Path, cache: Path) -> None:
    import logos.paths as paths
    import logos.data_loader as data_loader

    monkeypatch.setattr(paths, "DATA_RAW_DIR", raw, raising=False)
    monkeypatch.setattr(paths, "DATA_CACHE_DIR", cache, raising=False)
    monkeypatch.setattr(data_loader, "DATA_RAW_DIR", raw, raising=False)
    monkeypatch.setattr(data_loader, "DATA_CACHE_DIR", cache, raising=False)


def test_fetch_uses_fixture(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    cache = tmp_path / "cache"
    raw.mkdir()
    cache.mkdir()
    _patch_data_dirs(monkeypatch, raw, cache)
    _write_fixture(raw / "MSFT.csv")

    cli.main(
        [
            "fetch",
            "--symbol",
            "MSFT",
            "--asset-class",
            "equity",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-04",
            "--interval",
            "1d",
            "--cache-root",
            str(cache),
        ]
    )

    output = cache / "equity" / "MSFT_1d.csv"
    assert output.exists()
    meta = json.loads(output.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta.get("data_source") == "fixture"
    assert meta["output_interval"] == "1d"


def test_fetch_resample_creates_new_interval(monkeypatch, tmp_path):
    raw = tmp_path / "raw"
    cache = tmp_path / "cache"
    raw.mkdir()
    cache.mkdir()
    _patch_data_dirs(monkeypatch, raw, cache)
    _write_fixture(raw / "MSFT.csv")

    cli.main(
        [
            "fetch",
            "--symbol",
            "MSFT",
            "--asset-class",
            "equity",
            "--start",
            "2024-01-01",
            "--end",
            "2024-01-04",
            "--interval",
            "1d",
            "--output-interval",
            "1h",
            "--cache-root",
            str(cache),
        ]
    )

    output = cache / "equity" / "MSFT_1h.csv"
    assert output.exists()
    df = pd.read_csv(output, index_col=0, parse_dates=True)
    assert len(df) > 3
    meta = json.loads(output.with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["output_interval"] == "1h"
    assert meta["source_interval"] == "1d"
