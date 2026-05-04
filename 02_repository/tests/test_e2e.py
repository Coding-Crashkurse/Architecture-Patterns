from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PHASE_DIR = Path(__file__).resolve().parent.parent


def test_client_runs_against_real_server(server) -> None:
    result = subprocess.run(
        [sys.executable, "client.py"],
        cwd=PHASE_DIR,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"client failed.\nstdout:\n{result.stdout.decode()}\nstderr:\n{result.stderr.decode()}"
    )
