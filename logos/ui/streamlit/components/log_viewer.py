"""
Log viewer component with tail and regex filtering.

Displays log files with filtering and search capabilities.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from logos.ui.streamlit import data_access


def render_log_viewer(
    log_path: Path,
    title: str = "Log Viewer",
    default_lines: int = 200,
    show_controls: bool = True,
) -> None:
    """
    Render a log file viewer with tail and regex filtering.
    
    Args:
        log_path: Path to the log file.
        title: Viewer title.
        default_lines: Default number of lines to show.
        show_controls: Whether to show filter controls.
    """
    st.subheader(title)
    
    if not log_path.exists():
        st.warning(f"Log file not found: {log_path}")
        st.info("The log file will be created once the system starts logging.")
        return
    
    # Controls
    if show_controls:
        control_cols = st.columns([2, 2, 1])
        
        with control_cols[0]:
            num_lines = st.number_input(
                "Lines to show",
                min_value=10,
                max_value=1000,
                value=default_lines,
                step=10,
            )
        
        with control_cols[1]:
            pattern = st.text_input(
                "Filter (regex)",
                value="",
                placeholder="e.g., ERROR|WARNING",
            )
        
        with control_cols[2]:
            refresh = st.button("🔄 Refresh")
    else:
        num_lines = default_lines
        pattern = None
        refresh = False
    
    # Load log lines
    log_lines = data_access.tail_log(
        log_path,
        n=num_lines,
        pattern=pattern if pattern else None,
    )
    
    if not log_lines:
        st.info("No log entries found (or file is empty)")
        return
    
    # Display count
    st.markdown(f"**Showing {len(log_lines)} log lines** (newest first)")
    
    # Display in code block for better formatting
    log_text = "\n".join(log_lines)
    st.text_area(
        "Log Output",
        value=log_text,
        height=400,
        label_visibility="collapsed",
    )
    
    # Download button
    st.download_button(
        label="📥 Download Full Log",
        data=log_text,
        file_name=log_path.name,
        mime="text/plain",
    )


def render_inline_log(log_path: Path, n: int = 10) -> None:
    """
    Render a compact inline log view (for overview pages).
    
    Args:
        log_path: Path to the log file.
        n: Number of lines to show.
    """
    if not log_path.exists():
        st.caption("_No log file found_")
        return
    
    log_lines = data_access.tail_log(log_path, n=n)
    
    if not log_lines:
        st.caption("_Log file is empty_")
        return
    
    # Show last line prominently
    if log_lines:
        st.caption(f"**Latest:** {log_lines[0]}")
    
    # Show rest in expander
    if len(log_lines) > 1:
        with st.expander(f"Show {len(log_lines) - 1} more lines"):
            for line in log_lines[1:]:
                st.caption(line)
