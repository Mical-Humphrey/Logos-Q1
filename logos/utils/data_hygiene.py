from __future__ import annotations
import numpy as np
import pandas as pd

def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["dt", "open", "high", "low", "close", "volume"]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df = df.copy()
    df["dt"] = pd.to_datetime(df["dt"], utc=True)
    df = df.sort_values("dt").reset_index(drop=True)
    return df

def clean_numeric(df: pd.DataFrame, cols=("open", "high", "low", "close", "volume")) -> pd.DataFrame:
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=list(cols))
    return df