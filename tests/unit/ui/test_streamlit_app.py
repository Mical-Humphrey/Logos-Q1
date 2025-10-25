from __future__ import annotations

import importlib
import sys
import types
from typing import Any, Dict, List

from typing_extensions import Literal

import pytest

MODULE_NAME = "logos.ui.streamlit.app"


@pytest.fixture(autouse=True)
def _reset_module() -> None:
    sys.modules.pop(MODULE_NAME, None)


def test_streamlit_page_config_called(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: List[Dict[str, Any]] = []

    dummy_streamlit = types.ModuleType("streamlit")

    def record_config(**kwargs: Any) -> None:
        calls.append(kwargs)

    dummy_streamlit.set_page_config = record_config  # type: ignore[attr-defined]

    # Provide no-op placeholders for attributes that might be accessed later.
    def _noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    dummy_streamlit.columns = lambda *args, **kwargs: []  # type: ignore[attr-defined]
    dummy_streamlit.selectbox = _noop  # type: ignore[attr-defined]
    dummy_streamlit.title = _noop  # type: ignore[attr-defined]
    dummy_streamlit.subheader = _noop  # type: ignore[attr-defined]
    dummy_streamlit.info = _noop  # type: ignore[attr-defined]
    dummy_streamlit.caption = _noop  # type: ignore[attr-defined]
    dummy_streamlit.json = _noop  # type: ignore[attr-defined]
    dummy_streamlit.tabs = lambda labels: [_ContextManager() for _ in labels]  # type: ignore[attr-defined]
    dummy_streamlit.metric = _noop  # type: ignore[attr-defined]
    dummy_streamlit.line_chart = _noop  # type: ignore[attr-defined]
    dummy_streamlit.dataframe = _noop  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "streamlit", dummy_streamlit)

    importlib.import_module(MODULE_NAME)

    assert calls, "set_page_config was not invoked"
    assert calls[0]["layout"] == "wide"


class _ContextManager:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: Any) -> Literal[False]:
        return False
