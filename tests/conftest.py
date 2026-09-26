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
    config_mgr.set_app_context(logger.app_logger, "GPSMCPMMS demo")

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

    # A dedicated module with known constraints, used by the validation and
    # security tests: `n` is a bounded int (1..10), `secret` is protected.
    config_mgr.register_params(
        module_id="vtest",
        module_label="Validation test",
        param_dict={
            "n": {"type": "int", "label": "N", "bound_to": "1..10",
                  "default_val": 5},
            "secret": {"type": "int", "label": "Secret", "protected": True,
                       "default_val": 0},
        },
        callback=lambda value: None,
    )

    # A list whose members are known by their keys, for the rule that a key
    # may not be left empty. Registered here and not in the test file: modules
    # have to exist before any other ConfigManager does, or they are built
    # into whichever tree happens to be rooted at the time.
    config_mgr.register_params(
        module_id="klist",
        module_label="Keyed list",
        type_dict={
            "pair": {"rfid": {"label": "RFID", "type": "string"},
                     "sid": {"label": "Service", "type": "string"},
                     "note": {"label": "Note", "type": "string"}},
            "pair_list": {"list_member": {"type": "pair"},
                          "list_keys": [["rfid"], ["sid"]],
                          "list_size": "0.."},
        },
        param_dict={"cards": {"label": "Cards", "type": "pair_list"}},
        callback=lambda value: None,
    )

    # A list whose members carry a bounded value of their own, for the case a
    # release tightens a bound under values that are already stored. The
    # member takes its value while the node is being built, which is a
    # different code path from a plain parameter -- and the one that used to
    # be fatal.
    config_mgr.register_params(
        module_id="blist",
        module_label="Bounded list",
        type_dict={
            "timed": {"name": {"label": "Name", "type": "string"},
                      "seconds": {"label": "Seconds", "type": "int",
                                  "bound_to": "10..20", "default_val": 16}},
            "timed_list": {"list_member": {"type": "timed"},
                           "list_size": "0.."},
        },
        param_dict={"entries": {"label": "Entries", "type": "timed_list"}},
        callback=lambda value: None,
    )

    # Two rules that only make sense together, and the H4H application needs
    # both: a list whose members carry their own protection (a contact the
    # installer entered may be changed only with the password), and a member
    # that takes its options from a field outside its own list (the members
    # of a team are chosen among the people of that team's group).
    config_mgr.register_params(
        module_id="mplist",
        module_label="Protected members",
        func_dict={"get_people": _people_of, "get_groups": _groups},
        type_dict={
            "person": {
                "number": {"label": "Number", "type": "string"},
                "name": {"label": "Name", "type": "string"},
                "installed": {"label": "Entered by the installer",
                              "type": "boolean", "default_val": False},
            },
            "person_list": {"list_member": {"type": "person"},
                            "list_keys": [["number"]],
                            "list_size": "0..",
                            "protected_by": "installed"},
            "member_list": {"list_member": {"type": "enum",
                                            "values": "get_people",
                                            "values_for": "^group"},
                            "list_size": "0..5"},
            "team": {"group": {"label": "Group", "type": "enum",
                               "values": "get_groups"},
                     "members": {"label": "Members", "type": "member_list"}},
            "team_list": {"list_member": {"type": "team"},
                          "list_keys": [["group"]], "list_size": "0.."},
        },
        param_dict={"people": {"label": "People", "type": "person_list"},
                    "teams": {"label": "Teams", "type": "team_list"}},
        callback=lambda value: None,
    )

    return config_mgr


# The two providers behind "mplist": who belongs to which group, and the
# groups themselves. A provider that is handed the group answers with the
# people in it -- which is the whole point of a 'values_for' reaching out of
# its list.
_PEOPLE = {"0151": ("Ada", ("red", "blue")), "0152": ("Ben", ("blue",)),
           "0153": ("Cem", ("red",))}


def _people_of(group):
    return {number: {"label": name, "verbatim": True}
            for number, (name, groups) in _PEOPLE.items()
            if not group or group in groups}


def _groups():
    return {"red": {"label": "Red"}, "blue": {"label": "Blue"}}


def pytest_sessionfinish(session, exitstatus):
    # Remove the throwaway persistence directory created at import time.
    shutil.rmtree(_SANDBOX, ignore_errors=True)
