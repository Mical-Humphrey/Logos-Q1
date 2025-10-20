"""
Settings page for dashboard configuration.

Displays read-only redacted config view and controls for theme and refresh interval.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import streamlit as st

from logos import paths
from logos.ui.streamlit import state

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")

# Dashboard settings
st.subheader("📊 Dashboard Settings")

setting_cols = st.columns(2)

with setting_cols[0]:
    # Refresh interval
    refresh_interval = st.slider(
        "Auto-refresh Interval (seconds)",
        min_value=2,
        max_value=30,
        value=state.get_refresh_interval(),
        help="Controls auto-refresh rate for live monitoring pages"
    )
    state.set_refresh_interval(refresh_interval)
    
    st.success(f"Refresh interval set to {refresh_interval}s")

with setting_cols[1]:
    # Theme placeholder
    st.markdown("**Theme**")
    theme = st.selectbox(
        "Color Theme",
        ["Default", "Light", "Dark"],
        disabled=True,
        help="Theme switching coming soon"
    )
    st.info("💡 Theme customization is planned for a future release")

st.divider()

# Configuration view
st.subheader("🔧 Configuration (Read-Only)")

st.markdown("""
This section displays your current configuration with sensitive values redacted.

**Note:** This is a read-only view. To modify configuration, edit your `.env` file or environment variables.
""")

# Try to load .env file
env_file = paths.PROJECT_ROOT / ".env"
env_example_file = paths.PROJECT_ROOT / ".env.example"

sensitive_patterns = [
    r".*KEY.*",
    r".*SECRET.*",
    r".*TOKEN.*",
    r".*PASSWORD.*",
    r".*PASS.*",
    r".*API.*KEY.*",
    r".*PRIVATE.*",
]


def redact_sensitive(key: str, value: str) -> str:
    """Redact sensitive configuration values."""
    for pattern in sensitive_patterns:
        if re.match(pattern, key, re.IGNORECASE):
            if value and len(value) > 0:
                return "***REDACTED***"
            return ""
    return value


def load_env_file(file_path: Path) -> dict[str, str]:
    """Load environment variables from a file."""
    env_vars = {}
    if file_path.exists():
        try:
            with open(file_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        env_vars[key] = value
        except IOError:
            pass
    return env_vars


# Load configuration
if env_file.exists():
    st.markdown("**Source:** `.env` file")
    env_vars = load_env_file(env_file)
elif env_example_file.exists():
    st.markdown("**Source:** `.env.example` (template)")
    env_vars = load_env_file(env_example_file)
else:
    st.info("No configuration file found")
    env_vars = {}

# Display configuration
if env_vars:
    config_data = []
    
    for key, value in sorted(env_vars.items()):
        redacted_value = redact_sensitive(key, value)
        config_data.append({
            "Variable": key,
            "Value": redacted_value if redacted_value else "(empty)",
        })
    
    st.dataframe(config_data, use_container_width=True, hide_index=True)
    
    st.caption("🔒 Sensitive values (API keys, secrets, tokens) are automatically redacted")
else:
    st.info("No configuration variables found")

# Also show some environment variables
with st.expander("🌍 Environment Variables (Subset)"):
    st.markdown("Showing select LOGOS_* environment variables:")
    
    logos_vars = {
        k: v for k, v in os.environ.items()
        if k.startswith("LOGOS_")
    }
    
    if logos_vars:
        env_data = []
        for key, value in sorted(logos_vars.items()):
            redacted_value = redact_sensitive(key, value)
            env_data.append({
                "Variable": key,
                "Value": redacted_value if redacted_value else value,
            })
        
        st.dataframe(env_data, use_container_width=True, hide_index=True)
    else:
        st.info("No LOGOS_* environment variables set")

st.divider()

# Paths configuration
st.subheader("📁 Data Paths")

st.markdown("Key directories used by Logos-Q1:")

path_data = [
    {"Path": "Project Root", "Location": str(paths.PROJECT_ROOT)},
    {"Path": "Logos Dir", "Location": str(paths.LOGOS_DIR)},
    {"Path": "Docs Dir", "Location": str(paths.DOCS_DIR)},
    {"Path": "Data Dir", "Location": str(paths.DATA_DIR)},
    {"Path": "Runs Dir", "Location": str(paths.RUNS_DIR)},
    {"Path": "Live Sessions", "Location": str(paths.RUNS_LIVE_SESSIONS_DIR)},
    {"Path": "Logs Dir", "Location": str(paths.LOGS_DIR)},
]

st.dataframe(path_data, use_container_width=True, hide_index=True)

# Directory existence check
with st.expander("🔍 Directory Status"):
    for item in path_data:
        path_obj = Path(item["Location"])
        exists = path_obj.exists()
        status = "✅ Exists" if exists else "❌ Missing"
        st.markdown(f"**{item['Path']}**: {status}")

st.divider()

# About
st.subheader("ℹ️ About")

st.markdown("""
**Logos-Q1 Dashboard** — Phase 3 Visual Interface

- **Version**: 1.0.0 (Phase 3)
- **Mode**: Read-Only
- **Purpose**: Backtest analysis, live monitoring, and performance visualization

For more information, see:
- `README.md` in project root
- `docs/DASHBOARD.md` for dashboard documentation
- `docs/MANUAL.html` for full system manual
""")

st.info("💡 This dashboard never writes or modifies any files")
