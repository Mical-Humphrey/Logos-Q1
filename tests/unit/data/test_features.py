from __future__ import annotations

import pandas as pd
import pandas.testing as pdt

from logos.data import ColumnSpec, DataContract, FeatureStore


def _build_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"], utc=True)
    return pd.DataFrame({"value": [1.0, 2.0, 3.0]}, index=index)


def test_feature_store_register_and_load(tmp_path):
    store = FeatureStore(root=tmp_path / "features")
    contract = DataContract("basic", (ColumnSpec("value", "float"),))
    frame = _build_frame()
    version = store.register(
        "alpha",
        frame,
        contract=contract,
        params={"lookback": 3},
        code_hash="abc123",
        sources=["source.csv"],
    )
    assert version.path.exists()
    loaded, meta = store.load("alpha", version.version)
    pdt.assert_frame_equal(loaded, frame)
    assert meta["code_hash"] == "abc123"
    latest = store.latest_version("alpha")
    assert latest.version == version.version


def test_register_creates_new_version_on_change(tmp_path):
    store = FeatureStore(root=tmp_path / "features")
    contract = DataContract("basic", (ColumnSpec("value", "float"),))
    frame = _build_frame()
    v1 = store.register("alpha", frame, contract=contract, code_hash="hash1", params={}, sources=[])
    frame2 = frame.copy()
    frame2.loc[frame2.index[-1], "value"] = 5.0
    v2 = store.register("alpha", frame2, contract=contract, code_hash="hash1", params={}, sources=[])
    assert v1.version != v2.version
    latest_frame, meta = store.load("alpha")
    pdt.assert_frame_equal(latest_frame, frame2)
    assert meta["data_hash"] != meta["code_hash"]  # sanity check lineage keys exist
