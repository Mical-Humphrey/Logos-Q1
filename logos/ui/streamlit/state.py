"""
Session state management for Streamlit dashboard.

Manages user selections, refresh intervals, and theme preferences.
"""
from __future__ import annotations

import streamlit as st


def init_state() -> None:
    """Initialize session state with default values."""
    if "selected_run" not in st.session_state:
        st.session_state.selected_run = None
    
    if "selected_symbol" not in st.session_state:
        st.session_state.selected_symbol = None
    
    if "refresh_interval" not in st.session_state:
        st.session_state.refresh_interval = 5  # seconds
    
    if "theme" not in st.session_state:
        st.session_state.theme = "default"  # TODO: implement theme switching
    
    if "compare_mode" not in st.session_state:
        st.session_state.compare_mode = False
    
    if "run_a" not in st.session_state:
        st.session_state.run_a = None
    
    if "run_b" not in st.session_state:
        st.session_state.run_b = None


def get_refresh_interval() -> int:
    """Get the current refresh interval in seconds."""
    return st.session_state.get("refresh_interval", 5)


def set_refresh_interval(seconds: int) -> None:
    """Set the refresh interval in seconds."""
    st.session_state.refresh_interval = seconds


def get_selected_run() -> str | None:
    """Get the currently selected run identifier."""
    return st.session_state.get("selected_run")


def set_selected_run(run_id: str | None) -> None:
    """Set the currently selected run identifier."""
    st.session_state.selected_run = run_id


def get_compare_mode() -> bool:
    """Check if compare mode is enabled."""
    return st.session_state.get("compare_mode", False)


def set_compare_mode(enabled: bool) -> None:
    """Enable or disable compare mode."""
    st.session_state.compare_mode = enabled
