import subprocess
import sys
import time
from pathlib import Path


def test_run_demo_process():
    """Executes run_demo.py as a subprocess, checks initial startup output, then
    terminates it."""
    repo_root = Path(__file__).resolve().parent.parent
    demo_script = repo_root / "test_app" / "run_demo.py"

    proc = subprocess.Popen(
        [sys.executable, str(demo_script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=repo_root,
    )

    # Let the process initialize for 2 seconds
    time.sleep(2)

    # Send SIGINT (Ctrl+C) to trigger graceful shutdown
    proc.send_signal(subprocess.signal.SIGINT)
    stdout, stderr = proc.communicate(timeout=5)

    assert proc.returncode == 0 or proc.returncode == -2  # Exited 0 or
                                                          # interrupted cleanly
    assert ("App bereit" in stdout or
            "App bereit" in stderr or
            "Demo stopped" in stdout or
            "Demo stopped" in stderr
        )
