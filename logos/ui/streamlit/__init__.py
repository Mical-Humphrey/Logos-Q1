"""Streamlit dashboard scaffolding and safety defaults."""

from __future__ import annotations

import logging
import os


_LOGGER = logging.getLogger(__name__)
_TRUE_LITERALS = {"1", "true", "t", "yes", "y", "on"}

# Ensure Streamlit stays headless and avoids telemetry popups when executed in CI
# or unit tests. These defaults only apply when the user has not already
# configured the environment explicitly.
os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")
os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")


def _is_truthy_env(name: str) -> bool:
    raw = os.getenv(name)
    return bool(raw and raw.strip().lower() in _TRUE_LITERALS)


def configure_streamlit_binding(*, allow_remote: bool | None = None) -> str:
    """Set the Streamlit bind address, returning the host that will be used."""

    remote_requested = (
        allow_remote
        if allow_remote is not None
        else _is_truthy_env("LOGOS_DASHBOARD_ALLOW_REMOTE")
    )
    preferred_host = "0.0.0.0" if remote_requested else "127.0.0.1"

    current_host = os.environ.get("STREAMLIT_SERVER_ADDRESS")
    host = current_host or preferred_host

    if current_host is None:
        os.environ["STREAMLIT_SERVER_ADDRESS"] = host

    if host == "0.0.0.0":
        _LOGGER.warning(
            "dashboard_remote_binding_enabled host=%s advisory=protect_with_proxy",
            host,
        )
    else:
        _LOGGER.info("dashboard_binding host=%s", host)

    return host


__all__ = ["configure_streamlit_binding"]
