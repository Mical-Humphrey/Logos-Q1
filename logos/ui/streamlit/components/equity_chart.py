"""
Equity chart component using Plotly.

Renders equity curve with optional drawdown overlay.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots


def render_equity_chart(
    equity: pd.Series,
    title: str = "Equity Curve",
    show_drawdown: bool = True,
) -> None:
    """
    Render an interactive equity curve with Plotly.
    
    Args:
        equity: Pandas Series with equity values (indexed by date).
        title: Chart title.
        show_drawdown: Whether to show drawdown overlay.
    """
    if equity is None or len(equity) == 0:
        st.warning("No equity data available")
        return
    
    # Calculate drawdown if requested
    drawdown = None
    if show_drawdown:
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
    
    # Create subplot if showing drawdown
    if show_drawdown and drawdown is not None:
        fig = make_subplots(
            rows=2, cols=1,
            row_heights=[0.7, 0.3],
            subplot_titles=(title, "Drawdown"),
            vertical_spacing=0.1,
            shared_xaxes=True,
        )
        
        # Equity curve
        fig.add_trace(
            go.Scatter(
                x=equity.index,
                y=equity.values,
                mode="lines",
                name="Equity",
                line=dict(color="#1f77b4", width=2),
                hovertemplate="<b>%{x}</b><br>Equity: $%{y:,.2f}<extra></extra>",
            ),
            row=1, col=1
        )
        
        # Drawdown
        fig.add_trace(
            go.Scatter(
                x=drawdown.index,
                y=drawdown.values * 100,
                mode="lines",
                name="Drawdown",
                line=dict(color="#d62728", width=1),
                fill="tozeroy",
                fillcolor="rgba(214, 39, 40, 0.2)",
                hovertemplate="<b>%{x}</b><br>Drawdown: %{y:.2f}%<extra></extra>",
            ),
            row=2, col=1
        )
        
        # Update axes
        fig.update_xaxes(title_text="Date", row=2, col=1)
        fig.update_yaxes(title_text="Equity ($)", row=1, col=1)
        fig.update_yaxes(title_text="Drawdown (%)", row=2, col=1)
        
    else:
        # Single chart without drawdown
        fig = go.Figure()
        
        fig.add_trace(
            go.Scatter(
                x=equity.index,
                y=equity.values,
                mode="lines",
                name="Equity",
                line=dict(color="#1f77b4", width=2),
                hovertemplate="<b>%{x}</b><br>Equity: $%{y:,.2f}<extra></extra>",
            )
        )
        
        fig.update_layout(
            title=title,
            xaxis_title="Date",
            yaxis_title="Equity ($)",
        )
    
    # Common layout updates
    fig.update_layout(
        height=600 if show_drawdown else 500,
        hovermode="x unified",
        showlegend=True,
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)


def render_comparison_chart(
    equity_a: pd.Series,
    equity_b: pd.Series,
    label_a: str = "Run A",
    label_b: str = "Run B",
) -> None:
    """
    Render a comparison chart overlaying two equity curves.
    
    Args:
        equity_a: First equity series.
        equity_b: Second equity series.
        label_a: Label for first series.
        label_b: Label for second series.
    """
    if equity_a is None or equity_b is None:
        st.warning("Need two equity curves for comparison")
        return
    
    fig = go.Figure()
    
    # Normalize to 100 for easier comparison
    norm_a = (equity_a / equity_a.iloc[0]) * 100
    norm_b = (equity_b / equity_b.iloc[0]) * 100
    
    fig.add_trace(
        go.Scatter(
            x=norm_a.index,
            y=norm_a.values,
            mode="lines",
            name=label_a,
            line=dict(color="#1f77b4", width=2),
            hovertemplate=f"<b>%{{x}}</b><br>{label_a}: %{{y:.2f}}<extra></extra>",
        )
    )
    
    fig.add_trace(
        go.Scatter(
            x=norm_b.index,
            y=norm_b.values,
            mode="lines",
            name=label_b,
            line=dict(color="#ff7f0e", width=2),
            hovertemplate=f"<b>%{{x}}</b><br>{label_b}: %{{y:.2f}}<extra></extra>",
        )
    )
    
    fig.update_layout(
        title="Equity Comparison (Normalized to 100)",
        xaxis_title="Date",
        yaxis_title="Normalized Equity",
        height=500,
        hovermode="x unified",
        template="plotly_white",
    )
    
    st.plotly_chart(fig, use_container_width=True)
