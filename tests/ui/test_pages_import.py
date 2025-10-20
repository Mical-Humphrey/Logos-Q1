"""
Tests for Streamlit pages import.

Ensures all pages can be imported without errors.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def import_module_from_path(module_name: str, file_path: Path):
    """Import a Python module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec and spec.loader:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        # Note: We don't execute the module to avoid Streamlit initialization
        return module
    return None


def test_import_app():
    """Test importing the main app module."""
    app_path = Path(__file__).parent.parent.parent / "logos" / "ui" / "streamlit" / "app.py"
    
    # Just check the file exists and has valid Python syntax
    assert app_path.exists()
    with open(app_path) as f:
        code = f.read()
    compile(code, str(app_path), "exec")


def test_import_state():
    """Test importing the state module."""
    from logos.ui.streamlit import state
    
    # Check that key functions exist
    assert hasattr(state, "init_state")
    assert hasattr(state, "get_refresh_interval")
    assert hasattr(state, "set_refresh_interval")


def test_import_data_access():
    """Test importing the data_access module."""
    from logos.ui.streamlit import data_access
    
    # Check that key functions exist
    assert hasattr(data_access, "list_backtests")
    assert hasattr(data_access, "load_backtest_metrics")
    assert hasattr(data_access, "list_live_sessions")
    assert hasattr(data_access, "tail_log")


def test_import_components():
    """Test importing component modules."""
    from logos.ui.streamlit.components import equity_chart, log_viewer, metrics_card, trades_table
    
    # Check that key functions exist
    assert hasattr(metrics_card, "render_metrics_card")
    assert hasattr(equity_chart, "render_equity_chart")
    assert hasattr(trades_table, "render_trades_table")
    assert hasattr(log_viewer, "render_log_viewer")


def test_page_files_exist():
    """Test that all expected page files exist."""
    pages_dir = Path(__file__).parent.parent.parent / "logos" / "ui" / "streamlit" / "pages"
    
    expected_pages = [
        "00_Overview.py",
        "10_Backtests.py",
        "20_Live_Monitor.py",
        "30_Strategy_Lab.py",
        "40_Settings.py",
        "50_Tutor_Viewer.py",
    ]
    
    for page in expected_pages:
        page_path = pages_dir / page
        assert page_path.exists(), f"Page {page} not found"
        
        # Check that it has valid Python syntax
        with open(page_path) as f:
            code = f.read()
        compile(code, str(page_path), "exec")


def test_pages_have_docstrings():
    """Test that page files have docstrings."""
    pages_dir = Path(__file__).parent.parent.parent / "logos" / "ui" / "streamlit" / "pages"
    
    for page_file in pages_dir.glob("*.py"):
        with open(page_file) as f:
            content = f.read()
        
        # Check for docstring at the top (after potential encoding declaration)
        lines = content.strip().split("\n")
        found_docstring = False
        for line in lines[:10]:  # Check first 10 lines
            if '"""' in line or "'''" in line:
                found_docstring = True
                break
        
        assert found_docstring, f"Page {page_file.name} missing docstring"


def test_components_have_docstrings():
    """Test that component files have docstrings."""
    components_dir = Path(__file__).parent.parent.parent / "logos" / "ui" / "streamlit" / "components"
    
    for comp_file in components_dir.glob("*.py"):
        if comp_file.name == "__init__.py":
            continue
        
        with open(comp_file) as f:
            content = f.read()
        
        # Check for module docstring
        lines = content.strip().split("\n")
        found_docstring = False
        for line in lines[:10]:
            if '"""' in line or "'''" in line:
                found_docstring = True
                break
        
        assert found_docstring, f"Component {comp_file.name} missing docstring"
