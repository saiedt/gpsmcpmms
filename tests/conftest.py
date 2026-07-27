import os
import sys
import shutil
import tempfile
from pathlib import Path

# Sandbox every bit of persistence into a throwaway directory BEFORE the
# config_mgr singleton is imported (it is created at import time and reads
# these variables once). This keeps the suite hermetic and reproducible, and
# stops it from ever touching the real ~/.config/gpsmcpmms. setdefault() lets
# an explicit outer environment still point the tests elsewhere.
_SANDBOX = tempfile.mkdtemp(prefix="gpsmcpmms-test-")
os.environ.setdefault("GPSMCPMMS_CVV_DIR", os.path.join(_SANDBOX, "cvv"))
os.environ.setdefault("GPSMCPMMS_UI_DIR", os.path.join(_SANDBOX, "ui"))

import pytest

# Setup pathing for repo root and test_app
REPO_ROOT = Path(__file__).resolve().parent.parent
TEST_APP_DIR = REPO_ROOT / "test_app"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(TEST_APP_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_APP_DIR))

from gpsmcpmms import config_mgr


@pytest.fixture(scope="session", autouse=True)
def setup_demo_environment():
    """
    Registers logger, led, and sip modules with config_mgr once for the test
    session.
    """
    import logger
    config_mgr.switch_to_app_logger(logger.app_logger)

    import led
    import sip

    supported_states = [
        {"id": "off", "label": "Aus", "conf": {
            "is_continuous": True, "rgb": (0, 0, 0), "brightness": 0.0
        }},
        {"id": "booting", "label": "Wird Hochgefahren", "conf": {
            "is_continuous": True, "rgb": (255, 253, 85), "brightness": 0.03
        }}
    ]
    led.ledc.init_supported_states(supported_states)

    return config_mgr


def pytest_sessionfinish(session, exitstatus):
    # Remove the throwaway persistence directory created at import time.
    shutil.rmtree(_SANDBOX, ignore_errors=True)
