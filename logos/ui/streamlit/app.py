"""
Main entry point for Logos-Q1 Streamlit dashboard.

Launch with: streamlit run logos/ui/streamlit/app.py

This is a read-only visualization interface for backtests, live sessions,
metrics, and logs. No trading actions or file writes are performed.
"""
from __future__ import annotations

import streamlit as st

from logos.ui.streamlit import state


# Page configuration
st.set_page_config(
    page_title="Logos-Q1 Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize session state
state.init_state()

# Main page content
st.title("📊 Logos-Q1 Trading Dashboard")

st.markdown("""
Welcome to the **Logos-Q1 Visual Dashboard** — a read-only interface for exploring
backtests, monitoring live sessions, and analyzing trading performance.

### Quick Navigation

Use the sidebar to navigate between pages:

- **📈 Overview** — KPI tiles, recent backtests, and live session status
- **🔍 Backtests** — Detailed analysis of historical runs with metrics, charts, and trades
- **📡 Live Monitor** — Real-time account status, positions, and log streaming
- **🧪 Strategy Lab** — Explore available strategies and their configurations
- **⚙️ Settings** — View configuration and adjust dashboard preferences
- **📚 Tutor Viewer** — Browse lesson transcripts and learning materials

### Features

- **Read-only**: This dashboard never writes or mutates any files
- **Fast**: Uses mtime-based caching to minimize disk reads
- **Safe**: Gracefully handles missing or partial data files
- **Modular**: Components are reusable across different pages

### Getting Started

If you haven't run any backtests yet, try:

```bash
python -m logos.cli backtest --symbol MSFT --strategy mean_reversion --paper
```

Live trading sessions can be started with:

```bash
python -m logos.live trade --symbol BTC-USD --strategy momentum --interval 1m
```

Once you have data, use the pages above to explore your results!
""")

# Sidebar info
with st.sidebar:
    st.markdown("### Dashboard Info")
    st.info("""
    This is a **read-only** visualization interface.
    
    No trading actions or file modifications are performed from this dashboard.
    """)
    
    # Refresh interval control
    st.markdown("### Auto-Refresh")
    refresh_interval = st.slider(
        "Interval (seconds)",
        min_value=2,
        max_value=30,
        value=state.get_refresh_interval(),
        help="Controls auto-refresh rate for live monitoring pages"
    )
    state.set_refresh_interval(refresh_interval)
