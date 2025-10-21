from pathlib import Path

import pandas as pd
import pytest

from logos import data_loader
from logos.window import Window


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

    window = Window.from_bounds(start="2024-01-01", end="2024-01-05")
    df = data_loader.get_prices(symbol, window, asset_class="equity")

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

    window = Window.from_bounds(start="2024-01-01", end="2024-01-05")
    result = data_loader.get_prices(symbol, window, asset_class="equity")

    assert not result.empty
    assert cache_file.exists()

    cache_file.unlink(missing_ok=True)


def test_get_prices_blocks_synthetic_without_flag(monkeypatch, tmp_path):
    symbol = "UNITTEST_SYN"

    monkeypatch.setattr(data_loader, "DATA_RAW_DIR", tmp_path / "raw", raising=False)
    monkeypatch.setattr(
        data_loader,
        "resolve_cache_subdir",
        lambda asset: (tmp_path / "cache" / asset),
        raising=False,
    )
    monkeypatch.setattr(data_loader, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(data_loader, "_load_fixture", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        data_loader.yf, "download", lambda *args, **kwargs: pd.DataFrame()
    )

    with pytest.raises(data_loader.SyntheticDataNotAllowed):
        data_loader.get_prices(
            symbol,
            Window.from_bounds(start="2024-01-01", end="2024-01-05"),
            interval="1h",
            asset_class="equity",
        )


def test_get_prices_allows_synthetic_with_flag(monkeypatch, tmp_path):
    symbol = "UNITTEST_SYN_OK"

    monkeypatch.setattr(data_loader, "DATA_RAW_DIR", tmp_path / "raw", raising=False)
    monkeypatch.setattr(
        data_loader,
        "resolve_cache_subdir",
        lambda asset: (tmp_path / "cache" / asset),
        raising=False,
    )
    monkeypatch.setattr(data_loader, "ensure_dirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(data_loader, "_load_fixture", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        data_loader.yf, "download", lambda *args, **kwargs: pd.DataFrame()
    )

    called: dict[str, bool] = {"synthetic": False}

    def _fake_synth(sym, start, end, interval, meta=None):
        called["synthetic"] = True
        if meta is not None:
            meta["synthetic"] = True
            meta["data_source"] = "synthetic"
            meta["generator"] = data_loader.GENERATOR_VERSION
        idx = pd.date_range(start=start, periods=3, freq="D")
        return pd.DataFrame(
            {
                "Open": 1.0,
                "High": 1.0,
                "Low": 1.0,
                "Close": 1.0,
                "Adj Close": 1.0,
                "Volume": 1.0,
            },
            index=idx,
        )

    monkeypatch.setattr(data_loader, "_generate_synthetic_ohlcv", _fake_synth)

    window = Window.from_bounds(start="2024-01-01", end="2024-01-05")
    df = data_loader.get_prices(
        symbol,
        window,
        interval="1h",
        asset_class="equity",
        allow_synthetic=True,
    )

    assert called["synthetic"] is True
    assert not df.empty

    meta = data_loader.last_price_metadata()
    assert meta is not None
    assert meta["synthetic"] is True
    assert meta["data_source"] == "synthetic"
    assert meta["generator"] == data_loader.GENERATOR_VERSION
