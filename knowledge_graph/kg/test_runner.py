"""Run the legacy and RDF tests on a disposable copy, preserving root output/."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    started = datetime.now(timezone.utc).isoformat()
    print(f"Test start UTC: {started}", flush=True)
    with tempfile.TemporaryDirectory(prefix="esg_graph_test_") as temp:
        target = Path(temp) / "repo"
        shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(
            ".git", ".tmp", ".archive", ".venv", "__pycache__", "*.pyc"))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-B", "-W", "ignore::DeprecationWarning", "-m", "unittest", "discover", "-s", "tests", "-q"],
            cwd=target, env=env, check=False,
        )
    print(f"Test end UTC: {datetime.now(timezone.utc).isoformat()}; exit={result.returncode}", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
