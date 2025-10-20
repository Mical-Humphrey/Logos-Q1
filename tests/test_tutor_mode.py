import subprocess
import sys

def test_tutor_cli_lists_lessons():
    res = subprocess.run([sys.executable, "-m", "logos.tutor", "--list"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "mean_reversion" in res.stdout