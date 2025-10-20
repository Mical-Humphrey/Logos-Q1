"""
Trades table component with filters and CSV download.

Displays trade history with interactive filters and export capability.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_trades_table(trades: pd.DataFrame | None) -> None:
    """
    Render an interactive trades table with filters and CSV download.
    
    Args:
        trades: DataFrame containing trade records.
    """
    if trades is None or len(trades) == 0:
        st.info("No trades available")
        return
    
    st.subheader("📋 Trade History")
    
    # Create a copy for filtering
    filtered_trades = trades.copy()
    
    # Filter controls in columns
    filter_cols = st.columns(4)
    
    with filter_cols[0]:
        # Side filter
        if "side" in filtered_trades.columns:
            sides = ["All"] + sorted(filtered_trades["side"].unique().tolist())
            selected_side = st.selectbox("Side", sides)
            if selected_side != "All":
                filtered_trades = filtered_trades[filtered_trades["side"] == selected_side]
    
    with filter_cols[1]:
        # Symbol filter (if multiple symbols)
        if "symbol" in filtered_trades.columns:
            symbols = ["All"] + sorted(filtered_trades["symbol"].unique().tolist())
            if len(symbols) > 2:  # More than just "All" and one symbol
                selected_symbol = st.selectbox("Symbol", symbols)
                if selected_symbol != "All":
                    filtered_trades = filtered_trades[filtered_trades["symbol"] == selected_symbol]
    
    with filter_cols[2]:
        # Profitable trades filter
        if "pnl" in filtered_trades.columns or "profit" in filtered_trades.columns:
            pnl_col = "pnl" if "pnl" in filtered_trades.columns else "profit"
            pnl_filter = st.selectbox("P&L Filter", ["All", "Profitable", "Loss"])
            if pnl_filter == "Profitable":
                filtered_trades = filtered_trades[filtered_trades[pnl_col] > 0]
            elif pnl_filter == "Loss":
                filtered_trades = filtered_trades[filtered_trades[pnl_col] < 0]
    
    with filter_cols[3]:
        # Max rows to display
        max_rows = st.number_input(
            "Max Rows",
            min_value=10,
            max_value=1000,
            value=min(100, len(filtered_trades)),
            step=10,
        )
    
    # Show count
    st.markdown(f"**Showing {min(max_rows, len(filtered_trades))} of {len(filtered_trades)} trades**")
    
    # Display table
    display_df = filtered_trades.head(max_rows)
    
    # Format numeric columns
    if "pnl" in display_df.columns:
        display_df = display_df.copy()
        display_df["pnl"] = display_df["pnl"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")
    if "profit" in display_df.columns:
        display_df = display_df.copy()
        display_df["profit"] = display_df["profit"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")
    if "price" in display_df.columns:
        display_df = display_df.copy()
        display_df["price"] = display_df["price"].apply(lambda x: f"${x:,.2f}" if pd.notna(x) else "")
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
    )
    
    # Download button
    csv = filtered_trades.to_csv(index=False)
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="trades.csv",
        mime="text/csv",
    )
    
    # Summary statistics
    with st.expander("📊 Trade Statistics"):
        stat_cols = st.columns(4)
        
        with stat_cols[0]:
            st.metric("Total Trades", len(filtered_trades))
        
        with stat_cols[1]:
            if "pnl" in filtered_trades.columns:
                profitable = (filtered_trades["pnl"] > 0).sum()
                win_rate = (profitable / len(filtered_trades) * 100) if len(filtered_trades) > 0 else 0
                st.metric("Win Rate", f"{win_rate:.1f}%")
            elif "profit" in filtered_trades.columns:
                profitable = (filtered_trades["profit"] > 0).sum()
                win_rate = (profitable / len(filtered_trades) * 100) if len(filtered_trades) > 0 else 0
                st.metric("Win Rate", f"{win_rate:.1f}%")
        
        with stat_cols[2]:
            if "pnl" in filtered_trades.columns:
                total_pnl = filtered_trades["pnl"].sum()
                st.metric("Total P&L", f"${total_pnl:,.2f}")
            elif "profit" in filtered_trades.columns:
                total_profit = filtered_trades["profit"].sum()
                st.metric("Total Profit", f"${total_profit:,.2f}")
        
        with stat_cols[3]:
            if "pnl" in filtered_trades.columns and len(filtered_trades) > 0:
                avg_pnl = filtered_trades["pnl"].mean()
                st.metric("Avg P&L", f"${avg_pnl:,.2f}")
            elif "profit" in filtered_trades.columns and len(filtered_trades) > 0:
                avg_profit = filtered_trades["profit"].mean()
                st.metric("Avg Profit", f"${avg_profit:,.2f}")
