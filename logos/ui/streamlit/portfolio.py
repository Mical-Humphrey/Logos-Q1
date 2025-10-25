from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

import pandas as pd
import streamlit as st


def _format_currency(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"${value:,.2f}"


def _render_metric_grid(metrics: Dict[str, Any]) -> None:
    cols = st.columns(3)
    labels = [
        ("Net PnL", metrics.get("net_pnl")),
        ("Max Drawdown", metrics.get("max_drawdown")),
        ("Sharpe", metrics.get("sharpe")),
    ]
    for col, (label, value) in zip(cols, labels):
        with col:
            if isinstance(value, (int, float)):
                if label in {"Net PnL", "Max Drawdown"}:
                    col.metric(label, _format_currency(value))
                else:
                    col.metric(label, f"{value:.2f}")
            else:
                col.caption(f"{label}: not available")


def _render_table(data: Iterable[Dict[str, Any]], title: str) -> None:
    rows = list(data)
    if not rows:
        st.info(f"{title} not available for this run.")
        return
    df = pd.DataFrame(rows)
    st.caption(title)
    st.dataframe(df, use_container_width=True)


def render_portfolio_overview(run_path: Path, metrics: Dict[str, Any] | None) -> None:
    """Render a read-only overview of portfolio level metrics."""

    st.subheader("Portfolio Overview", divider="gray")
    if metrics is None:
        st.info("Metrics file missing or unreadable for the selected run.")
        return
    portfolio = metrics.get("portfolio") or {}
    if not portfolio:
        st.info("Portfolio metrics not recorded for this run.")
    else:
        _render_metric_grid(portfolio)
        breakdown = portfolio.get("breakdown")
        if isinstance(breakdown, dict):
            rows = [
                {"Segment": key, "Contribution": value}
                for key, value in sorted(breakdown.items())
            ]
            _render_table(rows, "Contribution by Segment")

    equity_csv = run_path / "equity.csv"
    if equity_csv.exists():
        try:
            equity_df = pd.read_csv(equity_csv, parse_dates=[0])
        except Exception as exc:  # pragma: no cover - defensive
            st.warning(f"Unable to load equity curve: {exc}")
        else:
            equity_df = equity_df.rename(columns={equity_df.columns[0]: "timestamp"})
            st.caption("Equity Curve (read-only)")
            st.line_chart(equity_df.set_index("timestamp"))
    summary_json = run_path / "summary.json"
    if summary_json.exists():
        try:
            summary = json.loads(summary_json.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = None
        if summary:
            st.caption("Snapshot Summary")
            st.json(summary)
