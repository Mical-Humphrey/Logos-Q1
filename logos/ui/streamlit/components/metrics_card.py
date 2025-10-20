"""
Metrics card component for displaying backtest performance metrics.

Renders CAGR, Sharpe, MaxDD, WinRate, Exposure in a visually appealing card format.
"""
from __future__ import annotations

from typing import Any

import streamlit as st


def render_metrics_card(metrics: dict[str, Any]) -> None:
    """
    Render a card with key performance metrics.
    
    Args:
        metrics: Dictionary containing metric values.
    """
    if not metrics:
        st.warning("No metrics available")
        return
    
    # Create columns for metrics
    cols = st.columns(5)
    
    # CAGR
    with cols[0]:
        cagr = metrics.get("cagr", metrics.get("annualized_return", 0))
        if isinstance(cagr, (int, float)):
            st.metric(
                label="CAGR",
                value=f"{cagr * 100:.2f}%",
                help="Compound Annual Growth Rate"
            )
        else:
            st.metric(label="CAGR", value="N/A")
    
    # Sharpe Ratio
    with cols[1]:
        sharpe = metrics.get("sharpe_ratio", metrics.get("sharpe", 0))
        if isinstance(sharpe, (int, float)):
            st.metric(
                label="Sharpe",
                value=f"{sharpe:.2f}",
                help="Risk-adjusted return metric"
            )
        else:
            st.metric(label="Sharpe", value="N/A")
    
    # Max Drawdown
    with cols[2]:
        max_dd = metrics.get("max_drawdown", metrics.get("max_dd", 0))
        if isinstance(max_dd, (int, float)):
            st.metric(
                label="Max Drawdown",
                value=f"{abs(max_dd) * 100:.2f}%",
                delta=None,
                delta_color="inverse",
                help="Maximum peak-to-trough decline"
            )
        else:
            st.metric(label="Max Drawdown", value="N/A")
    
    # Win Rate
    with cols[3]:
        win_rate = metrics.get("win_rate", 0)
        if isinstance(win_rate, (int, float)):
            st.metric(
                label="Win Rate",
                value=f"{win_rate * 100:.1f}%",
                help="Percentage of profitable trades"
            )
        else:
            st.metric(label="Win Rate", value="N/A")
    
    # Exposure
    with cols[4]:
        exposure = metrics.get("exposure", metrics.get("time_in_market", 0))
        if isinstance(exposure, (int, float)):
            st.metric(
                label="Exposure",
                value=f"{exposure * 100:.1f}%",
                help="Time in market"
            )
        else:
            st.metric(label="Exposure", value="N/A")
    
    # Additional metrics in expandable section
    with st.expander("📊 Additional Metrics"):
        extra_cols = st.columns(3)
        
        with extra_cols[0]:
            total_return = metrics.get("total_return", 0)
            if isinstance(total_return, (int, float)):
                st.metric("Total Return", f"{total_return * 100:.2f}%")
            
            num_trades = metrics.get("num_trades", metrics.get("total_trades", 0))
            st.metric("Total Trades", f"{num_trades}")
        
        with extra_cols[1]:
            avg_win = metrics.get("avg_win", 0)
            if isinstance(avg_win, (int, float)):
                st.metric("Avg Win", f"{avg_win * 100:.2f}%")
            
            avg_loss = metrics.get("avg_loss", 0)
            if isinstance(avg_loss, (int, float)):
                st.metric("Avg Loss", f"{abs(avg_loss) * 100:.2f}%")
        
        with extra_cols[2]:
            profit_factor = metrics.get("profit_factor", 0)
            if isinstance(profit_factor, (int, float)):
                st.metric("Profit Factor", f"{profit_factor:.2f}")
            
            sortino = metrics.get("sortino_ratio", metrics.get("sortino", 0))
            if isinstance(sortino, (int, float)):
                st.metric("Sortino", f"{sortino:.2f}")
