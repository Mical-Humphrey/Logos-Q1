from __future__ import annotations

from pathlib import Path


def test_no_yaml_load_calls() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[Path] = []
    self_path = Path(__file__).resolve()
    for path in root.rglob("*.py"):
        if "/.venv/" in str(path) or "/__pycache__/" in str(path):
            continue
        if path.resolve() == self_path:
            continue
        text = path.read_text(encoding="utf-8")
        if "yaml.load(" in text:
            offenders.append(path)
    assert (
        not offenders
    ), f"Unsafe yaml.load detected in: {', '.join(str(p) for p in offenders)}"
