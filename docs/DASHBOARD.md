# Logos-Q1 Dashboard Documentation

## Overview

The Logos-Q1 Dashboard is a read-only Streamlit-based visual interface for exploring backtests, monitoring live sessions, and analyzing trading performance. It provides an intuitive way to interact with your trading data without any risk of modifying files or executing trades.

## Features

- **Read-Only**: Never writes or mutates any files
- **Fast**: Uses mtime-based caching to minimize disk reads
- **Safe**: Gracefully handles missing or partial data files
- **Modular**: Reusable components across different pages
- **Real-Time**: Auto-refresh capabilities for live monitoring

## Installation

The dashboard dependencies are included in `requirements.txt`:

```bash
pip install -r requirements.txt
```

This will install:
- `streamlit>=1.28` - Web application framework
- `plotly>=5.18` - Interactive charting library
- All other existing dependencies

## Running the Dashboard

Launch the dashboard with:

```bash
streamlit run logos/ui/streamlit/app.py
```

The dashboard will open in your default web browser, typically at `http://localhost:8501`.

### Command Line Options

Streamlit supports various command-line options:

```bash
# Custom port
streamlit run logos/ui/streamlit/app.py --server.port 8502

# Custom host (for remote access)
streamlit run logos/ui/streamlit/app.py --server.address 0.0.0.0

# Disable file watcher (for production)
streamlit run logos/ui/streamlit/app.py --server.fileWatcherType none
```

## Pages

### Home (app.py)

The main landing page provides:
- Quick navigation links to all pages
- Overview of dashboard features
- Getting started instructions

### 📈 Overview (00_Overview.py)

Dashboard overview page showing:

**KPI Tiles:**
- Total backtest count
- Available strategies count
- Latest live P&L (if applicable)
- Last run timestamp

**Recent Backtests Table:**
- Last 10 backtests with key metrics
- Quick comparison of CAGR, Sharpe, and Max Drawdown

**Current Live Session:**
- Active session information
- Position summary
- Latest log entries

### 🔍 Backtests (10_Backtests.py)

Detailed backtest analysis with:

**Single Run Analysis:**
- Backtest selector with filters (symbol, strategy, date)
- Performance metrics cards (CAGR, Sharpe, Max DD, Win Rate, Exposure)
- Interactive equity curve with optional drawdown overlay
- Trades table with filters and CSV export

**Compare Mode:**
- Side-by-side comparison of two backtest runs
- Normalized equity curve overlay
- Metric deltas showing differences

### 📡 Live Monitor (20_Live_Monitor.py)

Real-time live session monitoring:

**Auto-Refresh:**
- Configurable refresh interval (2-10 seconds)
- Manual refresh button

**Account Panel:**
- Cash, total value, P&L, positions value
- P&L timeline chart

**Positions:**
- Current open positions table

**Recent Trades:**
- Last 20 trades in reverse chronological order

**Live Log:**
- Tail of live.log with regex filtering
- Download capability

### 🧪 Strategy Lab (30_Strategy_Lab.py)

Strategy exploration and documentation:

- List of all available strategies
- Module docstrings and function documentation
- Parameter schemas (if defined)
- Example CLI commands for backtesting and live trading
- Quick reference guide

### ⚙️ Settings (40_Settings.py)

Dashboard and system configuration:

**Dashboard Settings:**
- Auto-refresh interval control
- Theme selection (placeholder for future)

**Configuration View:**
- Read-only view of .env file
- Automatic redaction of sensitive values (API keys, secrets, tokens)
- Environment variables display

**Data Paths:**
- Key directory locations
- Directory existence status

### 📚 Tutor Viewer (50_Tutor_Viewer.py)

Browse lesson materials:

- List of generated lesson transcripts
- Markdown/text transcript viewing
- Plot/image display
- File listing for each lesson

## Components

Reusable UI components in `logos/ui/streamlit/components/`:

### metrics_card.py

Renders performance metrics in a card layout:
- Primary metrics: CAGR, Sharpe, Max DD, Win Rate, Exposure
- Expandable additional metrics: Total Return, Avg Win/Loss, Profit Factor, Sortino

### equity_chart.py

Plotly-based equity curve visualization:
- Interactive line chart with hover details
- Optional drawdown overlay (second subplot)
- Comparison mode for two equity curves (normalized)

### trades_table.py

Interactive trades table with:
- Filters: Side, Symbol, P&L (profitable/loss)
- Row limit control
- CSV download
- Summary statistics

### log_viewer.py

Log file viewer with:
- Tail N lines functionality
- Regex pattern filtering
- Full log download
- Inline compact view for overview pages

## Data Access Layer

`logos/ui/streamlit/data_access.py` provides read-only data loaders:

### Functions

- `list_backtests()` - List all backtest runs
- `load_backtest_metrics(path)` - Load metrics.json
- `load_backtest_equity(path)` - Load equity.csv
- `load_backtest_trades(path)` - Load trades.csv
- `list_live_sessions()` - List all live sessions
- `load_live_snapshot(path)` - Load account, positions, trades, orders
- `tail_log(path, n, pattern)` - Read log lines with optional filtering

### Caching

Uses simple mtime-based caching to avoid redundant file reads:
- Tracks file modification time
- Returns cached data if file unchanged
- TODO: Migrate to `st.cache_data` for better Streamlit integration

### Error Handling

All functions gracefully handle:
- Missing files (return None or empty list)
- Corrupted files (return None or empty dict)
- Invalid paths (return None or empty list)

## State Management

`logos/ui/streamlit/state.py` manages session state:

- `selected_run` - Currently selected backtest
- `selected_symbol` - Currently selected symbol
- `refresh_interval` - Auto-refresh interval (default 5s)
- `theme` - Theme preference (placeholder)
- `compare_mode` - Backtest comparison mode toggle
- `run_a`, `run_b` - Runs selected for comparison

## Testing

The dashboard includes comprehensive tests:

### tests/ui/test_data_access.py

Tests all data access functions with fixtures:
- List operations
- Load operations
- Missing file handling
- Metadata parsing

### tests/ui/test_pages_import.py

Tests page and component imports:
- Import validation
- Syntax checking
- Docstring validation

### Running Tests

```bash
# All tests including UI
pytest -q

# UI tests only
pytest tests/ui/ -v

# With coverage
pytest tests/ui/ --cov=logos.ui
```

## Development

### Adding a New Page

1. Create `logos/ui/streamlit/pages/NN_PageName.py`
2. Use numeric prefix (NN) for ordering
3. Include module docstring
4. Set page config: `st.set_page_config(title="...", icon="...")`
5. Import required components and data_access functions
6. Implement page logic
7. Add import test in `tests/ui/test_pages_import.py`

### Adding a New Component

1. Create `logos/ui/streamlit/components/component_name.py`
2. Include module docstring
3. Define `render_*()` function
4. Use Streamlit widgets and Plotly for charts
5. Handle None/empty data gracefully
6. Import in page files as needed

### Fixtures for Testing

Test fixtures are in `tests/fixtures/`:
- `backtests/` - Sample backtest runs
- `live/sessions/` - Sample live sessions
- `live.log` - Sample log file

## Troubleshooting

### Dashboard Won't Start

Check that dependencies are installed:
```bash
pip install -r requirements.txt
```

### No Data Showing

Ensure you have run at least one backtest:
```bash
python -m logos.cli backtest --symbol MSFT --strategy mean_reversion --paper
```

### Port Already in Use

Use a different port:
```bash
streamlit run logos/ui/streamlit/app.py --server.port 8502
```

### Live Monitor Shows Empty State

Start a live trading session:
```bash
python -m logos.live trade --symbol BTC-USD --strategy momentum --interval 1m
```

## Screenshots

> TODO: Add screenshots once dashboard is running
>
> - Home page
> - Overview with KPIs
> - Backtests analysis
> - Backtests compare mode
> - Live monitor
> - Strategy lab
> - Settings page

## Future Enhancements

- [ ] Migrate to `st.cache_data` for better caching
- [ ] Theme customization (light/dark modes)
- [ ] Advanced filtering and search
- [ ] Export reports to PDF
- [ ] Custom metric dashboards
- [ ] Performance optimization for large datasets
- [ ] Mobile-responsive layouts
- [ ] Real-time WebSocket updates for live data

## Support

For issues or questions:
1. Check this documentation
2. Review `README.md` for general setup
3. See `docs/MANUAL.html` for complete system documentation
4. Check test files for usage examples

## License

The dashboard is part of the Logos-Q1 project and follows the same MIT License.
