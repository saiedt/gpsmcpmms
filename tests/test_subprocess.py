"""Cross-process behaviour: persistence reload and env-var overrides.

The cvv tree is a process-global singleton, so a genuine reload (and a clean
env-var read) can only be exercised in a fresh interpreter.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

_WRITER = (
    "from gpsmcpmms import config_mgr\n"
    "from gpsmcpmms.cvv_tree import CvvNode\n"
    "config_mgr.register_params('rt', 'RT',"
    " {'n': {'type': 'int', 'label': 'N', 'default_val': 0}}, lambda v: None)\n"
    "CvvNode.update_module(config_mgr, 'rt', {'n': 4242})\n"
)
_READER = (
    "from gpsmcpmms import config_mgr\n"
    "config_mgr.register_params('rt', 'RT',"
    " {'n': {'type': 'int', 'label': 'N', 'default_val': 0}}, lambda v: None)\n"
    "print('VALUE=' + str(config_mgr.query('rt.n')['rt.n']))\n"
)
_PROBE = (
    "from gpsmcpmms import config_mgr as c\n"
    "print('P=%s T=%s' % (c._ui_port, c._session_timeout_seconds()))\n"
)


def _run(code, cvv_dir, ui_dir, **extra):
    env = dict(os.environ)
    env["GPSMCPMMS_CVV_DIR"] = str(cvv_dir)
    env["GPSMCPMMS_UI_DIR"] = str(ui_dir)
    env["GPSMCPMMS_NO_LANG_SEED"] = "1"
    env.update(extra)
    return subprocess.run([sys.executable, "-c", code], env=env,
                          capture_output=True, text=True, cwd=str(REPO_ROOT))


def test_value_persists_across_processes(tmp_path):
    """A value written by one process is reloaded by a fresh one (dump+journal)."""
    cvv, ui = tmp_path / "cvv", tmp_path / "ui"
    writer = _run(_WRITER, cvv, ui)
    assert writer.returncode == 0, writer.stderr
    reader = _run(_READER, cvv, ui)
    assert reader.returncode == 0, reader.stderr
    assert "VALUE=4242" in reader.stdout


def test_env_overrides_applied(tmp_path):
    out = _run(_PROBE, tmp_path / "cvv", tmp_path / "ui",
               GPSMCPMMS_UI_PORT="23456", GPSMCPMMS_SESSION_TIMEOUT="45")
    assert "P=23456 T=2700" in out.stdout, out.stderr


def test_env_bad_value_falls_back(tmp_path):
    out = _run(_PROBE, tmp_path / "cvv", tmp_path / "ui",
               GPSMCPMMS_UI_PORT="not-a-port", GPSMCPMMS_SESSION_TIMEOUT="99999")
    assert "P=8080 T=1800" in out.stdout, out.stderr
