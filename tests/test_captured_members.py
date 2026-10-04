"""A list of simple values whose members are captured (spec 4.6.2 A, 4.9.3).

A value hardware produces used to need a record around it: the capture button
lives on a field, and a list of simple values offers one field -- the member's
own -- which never had the button. These tests hold the three things that had
to be true for it to get one: the declaration is accepted, the list stays a
list of simple values (Case A, not a record list), and the capture arrives on
the member's path, group rule and all.

The module "caplist" in conftest declares two such lists under one roof, with
'distinct_values' spanning them: no telegram may serve as a button and as a
sensor.
"""

import threading
import time

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode, CvvPathElem

API = {"X-GPSMCPMMS-Api": "1"}

# The row that has no ordinal yet is addressed by the template's id, and that
# is the path a capture asks on -- for a record's field as much as here.
TEMPLATE = CvvPathElem.LIST_ITEM_TEMPLATE_ID
BUTTONS = f"caplist.senders.buttons.{TEMPLATE}"
SENSORS = f"caplist.senders.sensors.{TEMPLATE}"
# What the module hands handle_value_event(): one pattern per list, with no
# field name behind the '*' -- the members are the values themselves.
PATTERNS = ["caplist.senders.buttons.*", "caplist.senders.sensors.*"]


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c


def _seed(buttons=(), sensors=()):
    CvvNode.update_module(config_mgr, "caplist",
                          {"senders": {"buttons": list(buttons),
                                       "sensors": list(sensors)}})


def _token(client):
    return client.get("/api/cvv_data").get_json()["token"]


def _capture(client, path, value, within=5.0):
    """One capture, answered by the device the moment the editor waits.

    The answer comes from a thread rather than before the request, because
    the editor registers its waiter inside the request: a value handed over
    too early is discarded as a no-op, and the capture would then sit out its
    whole timeout. The thread is joined before the test goes on, so no
    answer ever outlives the capture it was meant for.
    """
    token = _token(client)

    def run():
        deadline = time.monotonic() + within
        while time.monotonic() < deadline:
            with config_mgr._lock:
                waiting = path in config_mgr._capture_waiters
            if waiting:
                config_mgr.handle_value_event(value, PATTERNS)
                return
            time.sleep(0.005)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        return client.get(f"/api/value/capture?path={path}",
                          headers={**API, "X-GPSMCPMMS-Token": token})
    finally:
        thread.join(timeout=within + 1)


def test_the_member_keeps_its_button(client):
    """The template travels with the button, and without children."""
    body = client.get("/api/cvv_data", headers=API).get_json()
    node = body["cvv"]["caplist"]["children"]["senders"]["children"]["buttons"]
    template = node["item_template"]
    assert template["ui"]["acquire_button"] == "Trigger the transmitter"
    # No children: this is what makes the editor build Case A. A record with
    # a single field would be Case B and look like one.
    assert "children" not in template
    assert template["path"] == BUTTONS


def test_a_captured_value_reaches_the_member(client):
    _seed()
    resp = _capture(client, BUTTONS, "1a2b3c,A")
    assert resp.status_code == 200
    assert resp.get_json()["value"] == "1a2b3c,A"


def test_a_free_value_passes_a_filled_group(client):
    _seed(buttons=["1a2b3c,A"], sensors=["4d5e6f,B"])
    resp = _capture(client, BUTTONS, "9f8e7d,C")
    assert resp.status_code == 200
    assert resp.get_json()["value"] == "9f8e7d,C"


def test_the_group_rule_spans_the_two_lists(client):
    """A telegram already serving as a sensor is refused as a button.

    Refused at capture and not at saving, because capture is the only way in
    for these values: being told afterwards that the transmitter is already
    known would come too late to be of any use.
    """
    _seed(sensors=["4d5e6f,B"])
    resp = _capture(client, BUTTONS, "4d5e6f,B")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Value already taken"


def test_the_rule_also_catches_the_list_it_is_captured_into(client):
    """The same value twice in one list is refused by the same rule.

    The group names both lists, so a list is its own participant: the row
    being added is a new one, and the member already holding the value is
    somebody else.
    """
    _seed(sensors=["4d5e6f,B"])
    resp = _capture(client, SENSORS, "4d5e6f,B")
    assert resp.status_code == 409
    assert resp.get_json()["error"] == "Value already taken"
