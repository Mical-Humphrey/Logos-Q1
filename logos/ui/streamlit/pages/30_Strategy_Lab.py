"""
Strategy Lab page for exploring available strategies.

Displays strategy modules, docstrings, parameter schemas, and example CLI commands.
"""
from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import streamlit as st

from logos import paths

st.set_page_config(page_title="Strategy Lab", page_icon="🧪", layout="wide")

st.title("🧪 Strategy Lab")

st.markdown("""
Explore available trading strategies, their documentation, and configuration options.

**Note:** This is a read-only view. No strategies are executed from this interface.
""")

# Find strategies
strategies_dir = paths.LOGOS_DIR / "strategies"

if not strategies_dir.exists():
    st.warning("Strategies directory not found")
    st.stop()

# List strategy modules
strategy_files = [
    f for f in strategies_dir.iterdir()
    if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
]

if not strategy_files:
    st.info("No strategy modules found")
    st.stop()

st.markdown(f"**Found {len(strategy_files)} strategy modules**")

# Strategy selector
strategy_names = [f.stem for f in strategy_files]
selected_strategy = st.selectbox("Select Strategy", strategy_names)

if selected_strategy:
    st.divider()
    
    # Load strategy module
    module_name = f"logos.strategies.{selected_strategy}"
    
    try:
        strategy_module = importlib.import_module(module_name)
        
        # Display module docstring
        st.subheader("📖 Description")
        
        module_doc = inspect.getdoc(strategy_module)
        if module_doc:
            st.markdown(module_doc)
        else:
            st.info("No module documentation available")
        
        st.divider()
        
        # Find main strategy functions
        st.subheader("🔧 Functions")
        
        functions = []
        for name, obj in inspect.getmembers(strategy_module):
            if inspect.isfunction(obj) and not name.startswith("_"):
                functions.append((name, obj))
        
        if functions:
            for func_name, func in functions:
                with st.expander(f"📌 {func_name}"):
                    func_doc = inspect.getdoc(func)
                    if func_doc:
                        st.markdown(func_doc)
                    
                    # Show signature
                    sig = inspect.signature(func)
                    st.code(f"{func_name}{sig}", language="python")
        else:
            st.info("No public functions found")
        
        st.divider()
        
        # Parameter schema (if available)
        st.subheader("⚙️ Parameters")
        
        # Check if there's a params class or dict
        if hasattr(strategy_module, "DEFAULT_PARAMS"):
            st.code(str(strategy_module.DEFAULT_PARAMS), language="python")
        elif hasattr(strategy_module, "PARAMS"):
            st.code(str(strategy_module.PARAMS), language="python")
        else:
            st.info("No default parameters defined")
        
        st.divider()
        
        # Example CLI commands
        st.subheader("💻 Example CLI Commands")
        
        st.markdown("**Basic backtest:**")
        st.code(
            f"python -m logos.cli backtest --symbol MSFT --strategy {selected_strategy} --paper",
            language="bash"
        )
        
        st.markdown("**With custom parameters:**")
        st.code(
            f"python -m logos.cli backtest --symbol MSFT --strategy {selected_strategy} "
            f"--params window=20,threshold=1.5 --paper",
            language="bash"
        )
        
        st.markdown("**Crypto with custom interval:**")
        st.code(
            f"python -m logos.cli backtest --symbol BTC-USD --strategy {selected_strategy} "
            f"--asset-class crypto --interval 1h --paper",
            language="bash"
        )
        
        st.markdown("**Live trading (paper mode):**")
        st.code(
            f"python -m logos.live trade --symbol BTC-USD --strategy {selected_strategy} "
            f"--interval 1m",
            language="bash"
        )
        
        st.warning(
            "⚠️ These are examples only. Review strategy code and test in paper mode "
            "before considering live execution."
        )
        
    except ImportError as e:
        st.error(f"Failed to import strategy module: {e}")
    except Exception as e:
        st.error(f"Error loading strategy: {e}")

st.divider()

# Quick reference
with st.expander("📚 Quick Reference"):
    st.markdown("""
    ### Strategy Development Guidelines
    
    1. **Signal Generation**: Strategies generate trading signals based on market data
    2. **Position Sizing**: Use consistent sizing rules across strategies
    3. **Risk Management**: Implement stop-losses and position limits
    4. **Testing**: Validate in backtests before live deployment
    5. **Documentation**: Document parameters, assumptions, and limitations
    
    ### Common Parameters
    
    - `window`: Lookback period for indicators
    - `threshold`: Signal threshold (z-score, percentage, etc.)
    - `fast`/`slow`: Moving average periods
    - `hedge_ratio`: For pairs trading strategies
    
    ### Resources
    
    - See `docs/MANUAL.html` for detailed strategy documentation
    - Check `docs/FINANCE.html` for strategy theory and case studies
    - Review `tests/` for strategy testing examples
    """)
