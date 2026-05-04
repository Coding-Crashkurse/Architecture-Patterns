"""Shared fixture: spin up server.py as a real subprocess for the test session."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest


PHASE_DIR = Path(__file__).resolve().parent.parent
PORT = 8001


@pytest.fixture(scope="session")
def server():
    proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=PHASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(50):
            try:
                r = httpx.get(f"http://127.0.0.1:{PORT}/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.RequestError:
                time.sleep(0.2)
        else:
            proc.terminate()
            out, err = proc.communicate(timeout=2)
            raise RuntimeError(
                f"server did not become healthy.\nstdout: {out.decode()}\nstderr: {err.decode()}"
            )
        yield
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
