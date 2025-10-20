"""
Backtests page for detailed analysis.

Displays metrics cards, equity charts, trades table, and comparison mode.
"""
from __future__ import annotations

import streamlit as st

from logos.ui.streamlit import data_access, state
from logos.ui.streamlit.components import equity_chart, metrics_card, trades_table

st.set_page_config(page_title="Backtests", page_icon="🔍", layout="wide")

st.title("🔍 Backtest Analysis")

# Load backtests
backtests = data_access.list_backtests()

if not backtests:
    st.warning("No backtests found")
    st.info("Run a backtest to see results here:")
    st.code("python -m logos.cli backtest --symbol MSFT --strategy mean_reversion --paper")
    st.stop()

# Sidebar filters
with st.sidebar:
    st.subheader("Filters")
    
    # Symbol filter
    all_symbols = sorted(set(bt.symbol for bt in backtests))
    selected_symbols = st.multiselect(
        "Symbols",
        options=all_symbols,
        default=all_symbols,
    )
    
    # Strategy filter
    all_strategies = sorted(set(bt.strategy for bt in backtests))
    selected_strategies = st.multiselect(
        "Strategies",
        options=all_strategies,
        default=all_strategies,
    )
    
    # Date range (simple text filter)
    date_filter = st.text_input(
        "Date Filter (prefix)",
        value="",
        help="Filter by timestamp prefix (e.g., '2024-01')"
    )
    
    # Apply filters
    filtered_backtests = [
        bt for bt in backtests
        if bt.symbol in selected_symbols
        and bt.strategy in selected_strategies
        and (not date_filter or bt.timestamp.startswith(date_filter))
    ]
    
    st.markdown(f"**{len(filtered_backtests)}** runs match filters")
    
    st.divider()
    
    # Compare mode toggle
    compare_mode = st.checkbox(
        "Compare Mode",
        value=state.get_compare_mode(),
        help="Compare two backtest runs side by side"
    )
    state.set_compare_mode(compare_mode)

# Main content
if compare_mode:
    st.subheader("📊 Compare Backtests")
    
    if len(filtered_backtests) < 2:
        st.warning("Need at least 2 backtests to compare")
        st.stop()
    
    # Run selectors
    col1, col2 = st.columns(2)
    
    run_options = [f"{bt.timestamp}_{bt.symbol}_{bt.strategy}" for bt in filtered_backtests]
    
    with col1:
        st.markdown("### Run A")
        run_a_idx = st.selectbox(
            "Select Run A",
            range(len(run_options)),
            format_func=lambda i: run_options[i],
            key="run_a_select",
        )
        run_a = filtered_backtests[run_a_idx]
    
    with col2:
        st.markdown("### Run B")
        run_b_idx = st.selectbox(
            "Select Run B",
            range(len(run_options)),
            format_func=lambda i: run_options[i],
            key="run_b_select",
        )
        run_b = filtered_backtests[run_b_idx]
    
    # Load data for both runs
    metrics_a = data_access.load_backtest_metrics(run_a.path)
    metrics_b = data_access.load_backtest_metrics(run_b.path)
    equity_a = data_access.load_backtest_equity(run_a.path)
    equity_b = data_access.load_backtest_equity(run_b.path)
    
    # Comparison chart
    if equity_a is not None and equity_b is not None:
        equity_chart.render_comparison_chart(
            equity_a,
            equity_b,
            label_a=f"{run_a.symbol} ({run_a.strategy})",
            label_b=f"{run_b.symbol} ({run_b.strategy})",
        )
    
    # Metrics comparison
    st.subheader("Metrics Comparison")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**{run_a.symbol} - {run_a.strategy}**")
        metrics_card.render_metrics_card(metrics_a)
    
    with col2:
        st.markdown(f"**{run_b.symbol} - {run_b.strategy}**")
        metrics_card.render_metrics_card(metrics_b)
    
    # Metric deltas
    st.subheader("Deltas (B - A)")
    delta_cols = st.columns(5)
    
    with delta_cols[0]:
        cagr_a = metrics_a.get("cagr", metrics_a.get("annualized_return", 0))
        cagr_b = metrics_b.get("cagr", metrics_b.get("annualized_return", 0))
        if isinstance(cagr_a, (int, float)) and isinstance(cagr_b, (int, float)):
            delta = (cagr_b - cagr_a) * 100
            st.metric("CAGR Delta", f"{delta:+.2f}%")
    
    with delta_cols[1]:
        sharpe_a = metrics_a.get("sharpe_ratio", metrics_a.get("sharpe", 0))
        sharpe_b = metrics_b.get("sharpe_ratio", metrics_b.get("sharpe", 0))
        if isinstance(sharpe_a, (int, float)) and isinstance(sharpe_b, (int, float)):
            delta = sharpe_b - sharpe_a
            st.metric("Sharpe Delta", f"{delta:+.2f}")
    
    with delta_cols[2]:
        dd_a = metrics_a.get("max_drawdown", metrics_a.get("max_dd", 0))
        dd_b = metrics_b.get("max_drawdown", metrics_b.get("max_dd", 0))
        if isinstance(dd_a, (int, float)) and isinstance(dd_b, (int, float)):
            delta = (dd_b - dd_a) * 100
            st.metric("Max DD Delta", f"{delta:+.2f}%", delta_color="inverse")
    
    with delta_cols[3]:
        wr_a = metrics_a.get("win_rate", 0)
        wr_b = metrics_b.get("win_rate", 0)
        if isinstance(wr_a, (int, float)) and isinstance(wr_b, (int, float)):
            delta = (wr_b - wr_a) * 100
            st.metric("Win Rate Delta", f"{delta:+.2f}%")
    
    with delta_cols[4]:
        trades_a = metrics_a.get("num_trades", metrics_a.get("total_trades", 0))
        trades_b = metrics_b.get("num_trades", metrics_b.get("total_trades", 0))
        delta = trades_b - trades_a
        st.metric("Trade Count Delta", f"{delta:+d}")

else:
    # Single run analysis
    st.subheader("Select Backtest Run")
    
    if not filtered_backtests:
        st.warning("No backtests match the current filters")
        st.stop()
    
    # Run picker
    run_options = [f"{bt.timestamp}_{bt.symbol}_{bt.strategy}" for bt in filtered_backtests]
    selected_idx = st.selectbox(
        "Backtest Run",
        range(len(run_options)),
        format_func=lambda i: run_options[i],
    )
    
    selected_run = filtered_backtests[selected_idx]
    state.set_selected_run(selected_run.run_id)
    
    # Load data
    metrics = data_access.load_backtest_metrics(selected_run.path)
    equity = data_access.load_backtest_equity(selected_run.path)
    trades = data_access.load_backtest_trades(selected_run.path)
    
    # Display metrics
    st.subheader("Performance Metrics")
    metrics_card.render_metrics_card(metrics)
    
    st.divider()
    
    # Display equity chart
    st.subheader("Equity Curve")
    if equity is not None:
        show_dd = st.checkbox("Show Drawdown Overlay", value=True)
        equity_chart.render_equity_chart(
            equity,
            title=f"{selected_run.symbol} - {selected_run.strategy}",
            show_drawdown=show_dd,
        )
    else:
        st.warning("No equity data found for this run")
    
    st.divider()
    
    # Display trades
    if trades is not None:
        trades_table.render_trades_table(trades)
    else:
        st.info("No trades data found for this run")
