from __future__ import annotations

from pathlib import Path

from core.io.quarantine import move_to_quarantine


def test_move_to_quarantine(tmp_path: Path) -> None:
    src = tmp_path / "bad.csv"
    content = "a,b,c\n1,2,3\n"
    src.write_text(content, encoding="utf-8")

    dest = move_to_quarantine(src, quarantine_root=tmp_path / "input_data" / "quarantine", reason="test")
    assert dest.exists()
    meta = dest.with_suffix(dest.suffix + ".quarantine.json")
    assert meta.exists()
    payload = meta.read_text(encoding="utf-8")
    assert "reason" in payload
    assert "sha256" in payload
    # original should be removed
    assert not src.exists()
