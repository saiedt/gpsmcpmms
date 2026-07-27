import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform == "win32",
                    reason="relies on POSIX SIGINT for graceful shutdown")
def test_run_demo_process(tmp_path):
    """Executes run_demo.py as a subprocess, checks initial startup output, then
    terminates it."""
    repo_root = Path(__file__).resolve().parent.parent
    demo_script = repo_root / "test_app" / "run_demo.py"

    # Isolate the demo's persistence from the rest of the suite.
    env = dict(os.environ)
    env["GPSMCPMMS_CVV_DIR"] = str(tmp_path / "cvv")
    env["GPSMCPMMS_UI_DIR"] = str(tmp_path / "ui")

    proc = subprocess.Popen(
        [sys.executable, str(demo_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=repo_root,
        env=env,
    )

    # Let the process initialize for 2 seconds
    time.sleep(2)

    # Send SIGINT (Ctrl+C) to trigger graceful shutdown
    proc.send_signal(signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=5)

    # Exited cleanly (0) or was interrupted by the signal (-SIGINT)
    assert proc.returncode == 0 or proc.returncode == -2
    assert ("App bereit" in stdout or
            "App bereit" in stderr or
            "Demo stopped" in stdout or
            "Demo stopped" in stderr)
