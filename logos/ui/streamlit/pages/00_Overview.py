"""
Overview page for Logos-Q1 Dashboard.

Displays KPI tiles, recent backtests, and current live session status.
"""
from __future__ import annotations

import streamlit as st

from logos import paths
from logos.ui.streamlit import data_access
from logos.ui.streamlit.components import log_viewer

st.set_page_config(page_title="Overview", page_icon="📈", layout="wide")

st.title("📈 Dashboard Overview")

# KPI Tiles
st.subheader("Key Metrics")

kpi_cols = st.columns(4)

# Backtest count
backtests = data_access.list_backtests()
with kpi_cols[0]:
    st.metric(
        label="Total Backtests",
        value=len(backtests),
        help="Number of completed backtest runs"
    )

# Strategies count (best effort)
strategies_count = 0
if paths.LOGOS_DIR.exists():
    strategies_dir = paths.LOGOS_DIR / "strategies"
    if strategies_dir.exists():
        strategies_count = len([
            f for f in strategies_dir.iterdir()
            if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
        ])

with kpi_cols[1]:
    st.metric(
        label="Strategies",
        value=strategies_count,
        help="Number of available strategy modules"
    )

# Latest live PnL (if present)
live_sessions = data_access.list_live_sessions()
latest_pnl = "N/A"
if live_sessions:
    latest_session = live_sessions[0]
    snapshot = data_access.load_live_snapshot(latest_session.path)
    if snapshot.get("account") is not None and len(snapshot["account"]) > 0:
        account_df = snapshot["account"]
        if "total_value" in account_df.columns:
            latest_value = account_df["total_value"].iloc[-1]
            initial_value = account_df["total_value"].iloc[0]
            pnl = latest_value - initial_value
            latest_pnl = f"${pnl:,.2f}"

with kpi_cols[2]:
    st.metric(
        label="Latest Live P&L",
        value=latest_pnl,
        help="P&L from most recent live session"
    )

# Last run timestamp
last_run = "Never"
if backtests:
    last_run = backtests[0].timestamp

with kpi_cols[3]:
    st.metric(
        label="Last Run",
        value=last_run,
        help="Timestamp of most recent backtest"
    )

st.divider()

# Recent Backtests
st.subheader("📊 Recent Backtests")

if backtests:
    # Display up to 10 most recent
    recent = backtests[:10]
    
    # Create table data
    table_data = []
    for bt in recent:
        metrics = data_access.load_backtest_metrics(bt.path)
        
        cagr = metrics.get("cagr", metrics.get("annualized_return", 0))
        sharpe = metrics.get("sharpe_ratio", metrics.get("sharpe", 0))
        max_dd = metrics.get("max_drawdown", metrics.get("max_dd", 0))
        
        table_data.append({
            "Timestamp": bt.timestamp,
            "Symbol": bt.symbol,
            "Strategy": bt.strategy,
            "CAGR": f"{cagr * 100:.2f}%" if isinstance(cagr, (int, float)) else "N/A",
            "Sharpe": f"{sharpe:.2f}" if isinstance(sharpe, (int, float)) else "N/A",
            "Max DD": f"{abs(max_dd) * 100:.2f}%" if isinstance(max_dd, (int, float)) else "N/A",
        })
    
    st.dataframe(table_data, use_container_width=True, hide_index=True)
    
    st.info("💡 Navigate to the **Backtests** page for detailed analysis")
else:
    st.info("No backtests found. Run a backtest to see results here.")
    st.code("python -m logos.cli backtest --symbol MSFT --strategy mean_reversion --paper")

st.divider()

# Current Live Session
st.subheader("📡 Current Live Session")

if live_sessions:
    latest_session = live_sessions[0]
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"**Session ID:** `{latest_session.session_id}`")
        st.markdown(f"**Started:** {latest_session.timestamp}")
        
        snapshot = data_access.load_live_snapshot(latest_session.path)
        
        if snapshot.get("positions") is not None:
            positions_df = snapshot["positions"]
            if len(positions_df) > 0:
                st.markdown(f"**Active Positions:** {len(positions_df)}")
                st.dataframe(positions_df.head(5), use_container_width=True)
        
        if snapshot.get("trades") is not None:
            trades_df = snapshot["trades"]
            st.markdown(f"**Total Trades:** {len(trades_df)}")
    
    with col2:
        # Latest log line
        st.markdown("**Latest Log Entry:**")
        log_viewer.render_inline_log(paths.LIVE_LOG_FILE, n=5)
    
    st.info("💡 Navigate to the **Live Monitor** page for real-time updates")
else:
    st.info("No live sessions found. Start a live trading session to see status here.")
    st.code("python -m logos.live trade --symbol BTC-USD --strategy momentum --interval 1m")
