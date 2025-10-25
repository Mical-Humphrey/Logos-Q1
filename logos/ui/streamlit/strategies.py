from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd
import streamlit as st


def _strategy_rows(strategies: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for name, payload in strategies.items():
        if not isinstance(payload, dict):
            continue
        yield {
            "Strategy": name,
            "Allocation": payload.get("allocation"),
            "Return": payload.get("return"),
            "Sharpe": payload.get("sharpe"),
            "Trades": payload.get("trades"),
        }


def render_strategy_panels(metrics: Dict[str, Any] | None) -> None:
    st.subheader("Strategies", divider="gray")
    if not metrics:
        st.info("Strategy metrics unavailable for this run.")
        return
    strategies = metrics.get("strategies")
    if not isinstance(strategies, dict) or not strategies:
        st.info("No per-strategy metrics captured.")
        return

    rows = list(_strategy_rows(strategies))
    if not rows:
        st.info("Strategy metrics missing or malformed.")
        return
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True)

    st.caption("Individual Strategy Details")
    for name, payload in strategies.items():
        if not isinstance(payload, dict):
            continue
        with st.expander(f"{name}"):
            st.json(payload)


def render_provenance_panel(run_path: Path) -> None:
    logs_dir = run_path / "logs"
    if logs_dir.exists():
        st.caption("Logs (read-only)")
        for candidate in sorted(logs_dir.glob("*.log")):
            st.write(f"- {candidate.name}")
    else:
        st.caption("Logs directory not present for this run.")
