import os
from pathlib import Path

import pandas as pd
import pytest

from logos import data_loader


def _fixture_df():
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    return pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104],
            "High": [101, 102, 103, 104, 105],
            "Low": [99, 100, 101, 102, 103],
            "Close": [100, 101, 102, 103, 104],
            "Adj Close": [100, 101, 102, 103, 104],
            "Volume": [1000, 1100, 1050, 1200, 1250],
        },
        index=dates,
    )


@pytest.fixture
def raw_dir(tmp_path, monkeypatch):
    project_raw = Path("input_data/raw")
    project_raw.mkdir(parents=True, exist_ok=True)
    yield project_raw
    for item in project_raw.glob("UNITTEST_*.csv"):
        item.unlink(missing_ok=True)


def test_get_prices_reads_from_raw_fixture(raw_dir):
    symbol = "UNITTEST_EQ"
    fixture_path = raw_dir / f"{symbol}.csv"
    _fixture_df().to_csv(fixture_path, index_label="Date")

    df = data_loader.get_prices(symbol, "2024-01-01", "2024-01-05", asset_class="equity")

    assert not df.empty
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
    assert df.index.min().strftime("%Y-%m-%d") == "2024-01-01"
    assert df.index.max().strftime("%Y-%m-%d") == "2024-01-05"

    fixture_path.unlink()


def test_get_prices_writes_cache_in_new_structure(monkeypatch):
    symbol = "UNITTEST_CACHE"
    cache_file = Path("input_data/cache/equity") / f"{symbol}_1d.csv"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.unlink(missing_ok=True)

    df = _fixture_df()

    def fake_download(*args, **kwargs):
        return df

    monkeypatch.setattr(data_loader.yf, "download", fake_download)

    result = data_loader.get_prices(symbol, "2024-01-01", "2024-01-05", asset_class="equity")

    assert not result.empty
    assert cache_file.exists()

    cache_file.unlink(missing_ok=True)
