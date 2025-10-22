from __future__ import annotations

import time
from pathlib import Path

from tools.retention_janitor import plan_and_execute


def test_retention_dry_run(tmp_path: Path) -> None:
    d = tmp_path / "runs"
    d.mkdir()
    # create a few files with mtime spaced
    for i in range(3):
        p = d / f"file{i}.txt"
        p.write_text("x" * (i + 1))
        # set mtime in the past
        p.touch()
        time.sleep(0.01)

    quotas = {"max_count": 2}
    res = plan_and_execute([d], quotas, enable=False, dry_run=True)
    assert "plan" in res
    assert len(res["plan"]) == 1


def test_retention_enable_delete(tmp_path: Path) -> None:
    d = tmp_path / "runs"
    d.mkdir()
    files = []
    for i in range(3):
        p = d / f"file{i}.txt"
        p.write_text("x" * (i + 1))
        files.append(p)
        time.sleep(0.01)

    quotas = {"max_count": 1}
    res = plan_and_execute([d], quotas, enable=True, dry_run=False)
    assert "deleted" in res
    # exactly 2 deletions should have occurred
    assert len(res["deleted"]) == 2
    for deleted in res["deleted"]:
        assert not Path(deleted).exists()
