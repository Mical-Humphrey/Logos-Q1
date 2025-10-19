import pytest

from logos.cli import periods_per_year


def test_periods_per_year_equity_daily():
    assert periods_per_year("equity", "1d") == 252


def test_periods_per_year_equity_intraday():
    assert periods_per_year("equity", "1h") == 252 * 24
    assert periods_per_year("equity", "60m") == 252 * 24


def test_periods_per_year_crypto_daily():
    assert periods_per_year("crypto", "1d") == 365


def test_periods_per_year_forex_alias_and_interval():
    assert periods_per_year("fx", "30m") == 260 * 48
    assert periods_per_year("forex", "5m") == 260 * 288


@pytest.mark.parametrize(
    "asset,interval",
    [
        ("equity", "15m"),
        ("crypto", "10m"),
        ("forex", "1d"),
    ],
)
def test_periods_per_year_handles_known_pairs(asset, interval):
    assert periods_per_year(asset, interval) > 0
