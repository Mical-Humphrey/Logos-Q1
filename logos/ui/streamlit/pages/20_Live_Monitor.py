"""
Live Monitor page for real-time session monitoring.

Displays account, positions, recent fills, P&L timeline, and log tail.
"""
from __future__ import annotations

import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from logos import paths
from logos.ui.streamlit import data_access, state
from logos.ui.streamlit.components import log_viewer

st.set_page_config(page_title="Live Monitor", page_icon="📡", layout="wide")

st.title("📡 Live Monitor")

# Auto-refresh controls
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    auto_refresh = st.checkbox(
        "Auto-refresh",
        value=True,
        help="Automatically refresh data at the specified interval"
    )

with col2:
    refresh_interval = st.slider(
        "Refresh Interval (seconds)",
        min_value=2,
        max_value=10,
        value=state.get_refresh_interval(),
    )
    state.set_refresh_interval(refresh_interval)

with col3:
    manual_refresh = st.button("🔄 Refresh Now")

# Load sessions
live_sessions = data_access.list_live_sessions()

if not live_sessions:
    st.warning("No live sessions found")
    st.info(
        "Start a live trading session to monitor it here:\n\n"
        "```bash\n"
        "python -m logos.live trade --symbol BTC-USD --strategy momentum --interval 1m\n"
        "```"
    )
    st.stop()

# Session selector
session_options = [f"{s.session_id}" for s in live_sessions]
selected_session_idx = st.selectbox(
    "Select Session",
    range(len(session_options)),
    format_func=lambda i: session_options[i],
)

selected_session = live_sessions[selected_session_idx]

st.markdown(f"**Session:** `{selected_session.session_id}`")
st.markdown(f"**Started:** {selected_session.timestamp}")

# Load snapshot
snapshot = data_access.load_live_snapshot(selected_session.path)

st.divider()

# Account panel
st.subheader("💰 Account")

account_df = snapshot.get("account")
if account_df is not None and len(account_df) > 0:
    # Show latest account state
    latest = account_df.iloc[-1]
    
    acc_cols = st.columns(4)
    
    with acc_cols[0]:
        cash = latest.get("cash", 0)
        st.metric("Cash", f"${cash:,.2f}")
    
    with acc_cols[1]:
        total_value = latest.get("total_value", 0)
        st.metric("Total Value", f"${total_value:,.2f}")
    
    with acc_cols[2]:
        if "total_value" in account_df.columns and len(account_df) > 1:
            initial_value = account_df["total_value"].iloc[0]
            current_value = latest.get("total_value", 0)
            pnl = current_value - initial_value
            pnl_pct = (pnl / initial_value * 100) if initial_value > 0 else 0
            st.metric("P&L", f"${pnl:,.2f}", f"{pnl_pct:+.2f}%")
        else:
            st.metric("P&L", "N/A")
    
    with acc_cols[3]:
        positions_value = latest.get("positions_value", 0)
        st.metric("Positions Value", f"${positions_value:,.2f}")
    
    # P&L timeline chart
    if "total_value" in account_df.columns and len(account_df) > 1:
        st.subheader("📈 P&L Timeline")
        
        fig = go.Figure()
        
        # Assume index or a timestamp column exists
        if account_df.index.name or isinstance(account_df.index, pd.DatetimeIndex):
            x_data = account_df.index
        elif "timestamp" in account_df.columns:
            x_data = pd.to_datetime(account_df["timestamp"])
        else:
            x_data = range(len(account_df))
        
        fig.add_trace(
            go.Scatter(
                x=x_data,
                y=account_df["total_value"],
                mode="lines+markers",
                name="Total Value",
                line=dict(color="#1f77b4", width=2),
            )
        )
        
        fig.update_layout(
            xaxis_title="Time",
            yaxis_title="Total Value ($)",
            height=300,
            template="plotly_white",
        )
        
        st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No account data available")

st.divider()

# Positions panel
st.subheader("📊 Positions")

positions_df = snapshot.get("positions")
if positions_df is not None and len(positions_df) > 0:
    st.dataframe(positions_df, use_container_width=True, hide_index=True)
else:
    st.info("No open positions")

st.divider()

# Recent fills
st.subheader("📋 Recent Trades")

trades_df = snapshot.get("trades")
if trades_df is not None and len(trades_df) > 0:
    # Show last 20 trades
    recent_trades = trades_df.tail(20).iloc[::-1]  # Reverse to show newest first
    st.dataframe(recent_trades, use_container_width=True, hide_index=True)
else:
    st.info("No trades yet")

st.divider()

# Live log tail
st.subheader("📝 Live Log")

if paths.LIVE_LOG_FILE.exists():
    log_viewer.render_log_viewer(
        paths.LIVE_LOG_FILE,
        title="",
        default_lines=100,
        show_controls=True,
    )
else:
    st.info("Live log file not found")

# Auto-refresh implementation
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
