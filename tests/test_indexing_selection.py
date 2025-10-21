from __future__ import annotations

import pandas as pd
import pytest

from logos.utils.indexing import adjust_at, adjust_from, last_row, last_value


SeriesBase = pd.Series
DataFrameBase = pd.DataFrame


class SpySeries(SeriesBase):
    loc_get_keys: list[object] = []
    loc_set_keys: list[object] = []
    iloc_get_keys: list[object] = []
    iloc_set_keys: list[object] = []

    @property
    def _constructor(self):  # type: ignore[override]
        return SpySeries

    @property
    def loc(self):  # type: ignore[override]
        base = SeriesBase.loc.__get__(self, SeriesBase)

        class _SpyLoc:
            def __getitem__(_, key):
                SpySeries.loc_get_keys.append(key)
                return base[key]

            def __setitem__(_, key, value):
                SpySeries.loc_set_keys.append(key)
                base[key] = value

        return _SpyLoc()

    @property
    def iloc(self):  # type: ignore[override]
        base = SeriesBase.iloc.__get__(self, SeriesBase)

        class _SpyILoc:
            def __getitem__(_, key):
                SpySeries.iloc_get_keys.append(key)
                return base[key]

            def __setitem__(_, key, value):
                SpySeries.iloc_set_keys.append(key)
                base[key] = value

            def _setitem_with_indexer(_, indexer, value, name):  # type: ignore[override]
                base._setitem_with_indexer(indexer, value, name)

        return _SpyILoc()


class SpyDataFrame(DataFrameBase):
    iloc_get_keys: list[object] = []
    iloc_set_keys: list[object] = []

    @property
    def _constructor(self):  # type: ignore[override]
        return SpyDataFrame

    @property
    def iloc(self):  # type: ignore[override]
        base = DataFrameBase.iloc.__get__(self, DataFrameBase)

        class _SpyILoc:
            def __getitem__(_, key):
                SpyDataFrame.iloc_get_keys.append(key)
                return base[key]

            def __setitem__(_, key, value):
                SpyDataFrame.iloc_set_keys.append(key)
                base[key] = value

        return _SpyILoc()


@pytest.fixture(autouse=True)
def _reset_spies() -> None:
    SpySeries.loc_get_keys = []
    SpySeries.loc_set_keys = []
    SpySeries.iloc_get_keys = []
    SpySeries.iloc_set_keys = []
    SpyDataFrame.iloc_get_keys = []
    SpyDataFrame.iloc_set_keys = []


def test_indexing_adjust_from_uses_loc_with_timestamp() -> None:
    idx = pd.date_range("2024-01-01", periods=4, freq="D", tz="UTC")
    series = SpySeries([0.0, 0.0, 0.0, 0.0], index=idx)

    adjust_from(series, idx[2], 5.0)

    loc_get = list(SpySeries.loc_get_keys)
    loc_set = list(SpySeries.loc_set_keys)
    iloc_get = list(SpySeries.iloc_get_keys)
    iloc_set = list(SpySeries.iloc_set_keys)
    values = series.tolist()

    assert loc_get == [slice(idx[2], None, None)]
    assert loc_set == [slice(idx[2], None, None)]
    assert iloc_get == []
    assert iloc_set == []
    assert values[:2] == [0.0, 0.0]
    assert values[2:] == [5.0, 5.0]


def test_indexing_adjust_at_uses_loc_with_timestamp() -> None:
    idx = pd.date_range("2024-02-01", periods=3, freq="h", tz="UTC")
    series = SpySeries([1.0, 1.0, 1.0], index=idx)

    adjust_at(series, idx[1], -0.25)

    loc_get = list(SpySeries.loc_get_keys)
    loc_set = list(SpySeries.loc_set_keys)
    iloc_get = list(SpySeries.iloc_get_keys)
    iloc_set = list(SpySeries.iloc_set_keys)
    values = series.tolist()

    assert loc_get == [idx[1]]
    assert loc_set == [idx[1]]
    assert iloc_get == []
    assert iloc_set == []
    assert values[0] == pytest.approx(1.0)
    assert values[1] == pytest.approx(0.75)
    assert values[2] == pytest.approx(1.0)


def test_indexing_last_value_uses_iloc() -> None:
    series = SpySeries([10, 20, 30], index=pd.RangeIndex(start=0, stop=3))

    assert last_value(series) == 30
    assert SpySeries.iloc_get_keys == [-1]
    assert SpySeries.loc_get_keys == []


def test_indexing_last_row_uses_iloc() -> None:
    frame = SpyDataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.date_range("2024-03-01", periods=3, freq="D", tz="UTC"),
    )

    row = last_row(frame)

    assert pytest.approx(row["Close"]) == 3.0
    assert SpyDataFrame.iloc_get_keys == [-1]
    assert SpyDataFrame.iloc_set_keys == []
