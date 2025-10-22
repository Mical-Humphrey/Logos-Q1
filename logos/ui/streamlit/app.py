from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

import streamlit as st

from logos.paths import RUNS_DIR
from . import configure_streamlit_binding

configure_streamlit_binding()

logger = logging.getLogger(__name__)


def _list_runs() -> List[Path]:
    root = RUNS_DIR
    if not root.exists():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir())


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.info(f"Missing artifact: {path}")
    except json.JSONDecodeError as exc:
        st.warning(f"Corrupt artifact {path}: {exc}")
    except Exception as exc:  # pragma: no cover - defensive
        st.error(f"Error loading {path}: {exc}")
    return None


def render_dashboard() -> None:
    st.title("Logos Dashboard (Read-Only)")
    runs = _list_runs()
    if not runs:
        st.info("No runs available.")
        return
    selection = st.selectbox("Select run", runs, format_func=lambda p: p.name)
    if selection is None:
        return
    metrics_path = selection / "metrics.json"
    metrics = _load_json(metrics_path)
    if metrics is not None:
        st.subheader("Metrics")
        st.json(metrics)
    provenance_path = selection / "provenance.json"
    provenance = _load_json(provenance_path)
    if provenance is not None:
        st.subheader("Provenance")
        st.json(provenance)


def main() -> None:
    render_dashboard()


if __name__ == "__main__":  # pragma: no cover
    main()
