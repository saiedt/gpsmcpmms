"""A list of options that can be asked for again (spec 4.9.1).

A dynamic enum is fetched once, when its field is drawn, and kept until the
panel is saved. That suits a list of voices or service types; it does not
suit the devices a radio can see, which change while somebody is holding one
in pairing mode. 'refreshable' gives such a field a button, and the provider
is told which of the two it is answering: the drawing, which asks what is
known, or the button, which asks it to look again.
"""

import json

import pytest

from gpsmcpmms.cvv_tree import CvvError, CvvNode

API = {"X-GPSMCPMMS-Api": "1"}

# What the provider was asked, in order: the value of 'refresh' each time.
ASKED = []


def _devices(refresh=False):
    ASKED.append(refresh)
    seen = {"aa": {"label": "Known", "verbatim": True}}
    if refresh:
        seen["bb"] = {"label": "Just found", "verbatim": True}
    return seen


def _devices_of(kind, refresh=False):
    ASKED.append((kind, refresh))
    return {"aa": {"label": "Known", "verbatim": True}}


def _nobody_to_ask():
    return {"aa": {"label": "Known", "verbatim": True}}


PARAMS = {
    "device": {"label": "Device", "type": "enum", "values": "get_devices",
               "refreshable": True},
    "steady": {"label": "Steady", "type": "enum", "values": "get_devices"},
    "kind": {"label": "Kind", "type": "enum",
             "values": {"speaker": {"label": "Speaker"}}},
    "device_of_kind": {"label": "Device of that kind", "type": "enum",
                       "values": "get_devices_of", "values_for": "kind",
                       "refreshable": True},
}


@pytest.fixture(scope="module")
def mgr(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.register_params(module_id="radio", module_label="Radio",
                        param_dict=PARAMS, callback=lambda value: None,
                        func_dict={"get_devices": _devices,
                                   "get_devices_of": _devices_of})
    return cfg


@pytest.fixture
def client(mgr):
    mgr.start_editor(run_server=False)
    mgr._flask_app.config["TESTING"] = True
    mgr._invalidate_session("test fixture starting from a clean session")
    with mgr._flask_app.test_client() as c:
        yield c


def _token(client):
    return client.get("/api/cvv_data").get_json()["token"]


def _ask(client, path, extra=""):
    token = _token(client)
    return client.get(f"/api/config/enum-options?path={path}{extra}",
                      headers={**API, "X-GPSMCPMMS-Token": token})


def _constraints(mgr, name):
    nodes = json.loads(CvvNode.get_cvv_json_dump(mgr))["radio"]["children"]
    return nodes[name]["constraints"]


def test_the_schema_says_which_list_can_be_asked_for_again(mgr):
    # The editor draws the button from this and from nothing else.
    assert _constraints(mgr, "device").get("refreshable") is True
    assert "refreshable" not in _constraints(mgr, "steady")


def test_drawing_the_field_does_not_ask_the_device_to_look(client):
    ASKED.clear()
    resp = _ask(client, "radio.device")
    assert resp.status_code == 200
    assert set(resp.get_json()["values"]) == {"aa"}
    assert ASKED == [False]


def test_the_button_asks_it_to_look_again(client):
    ASKED.clear()
    resp = _ask(client, "radio.device", "&refresh=1")
    assert set(resp.get_json()["values"]) == {"aa", "bb"}
    assert ASKED == [True]


def test_a_list_that_is_not_refreshable_is_not_told_anything(client):
    # The same provider, declared without the key: 'refresh' in the request
    # is then nobody's business, and the provider keeps its default.
    ASKED.clear()
    resp = _ask(client, "radio.steady", "&refresh=1")
    assert set(resp.get_json()["values"]) == {"aa"}
    assert ASKED == [False]


def test_it_goes_together_with_values_for(client):
    ASKED.clear()
    resp = _ask(client, "radio.device_of_kind", '&arg="speaker"&refresh=1')
    assert resp.status_code == 200
    assert ASKED == [("speaker", True)]


# --------------------------------------------------------------------------
# What is refused at registration
# --------------------------------------------------------------------------

def _register(mgr, module_id, decl, funcs, types=None):
    mgr.register_params(module_id=module_id, module_label=module_id,
                        param_dict={"field": decl}, type_dict=types,
                        callback=lambda value: None, func_dict=funcs)


def test_a_provider_that_cannot_be_told_is_refused(mgr):
    # It would fail on the first click, with a stack trace in the log and
    # nothing naming the declaration.
    with pytest.raises(ValueError, match="keyword 'refresh'"):
        _register(mgr, "radio-deaf",
                  {"label": "Device", "type": "enum", "values": "get",
                   "refreshable": True},
                  {"get": _nobody_to_ask})


def test_only_a_dynamic_enum_has_anybody_to_ask(mgr):
    with pytest.raises(CvvError, match="needs a dynamic enum"):
        _register(mgr, "radio-static",
                  {"label": "Kind", "type": "enum", "refreshable": True,
                   "values": {"speaker": {"label": "Speaker"}}}, {})
    with pytest.raises(CvvError, match="needs a dynamic enum"):
        _register(mgr, "radio-string",
                  {"label": "Name", "type": "string", "refreshable": True},
                  {})


def test_it_is_a_yes_or_a_no(mgr):
    with pytest.raises(CvvError, match="True or False"):
        _register(mgr, "radio-word",
                  {"label": "Device", "type": "enum", "values": "get",
                   "refreshable": "yes"},
                  {"get": _devices})


def test_a_member_of_a_simple_list_has_no_row_for_the_button(mgr):
    with pytest.raises(CvvError, match="members of a simple list"):
        _register(mgr, "radio-list",
                  {"label": "Devices", "type": "device_list"},
                  {"get": _devices},
                  types={"device_list": {
                      "list_member": {"type": "enum", "values": "get",
                                      "refreshable": True},
                      "list_size": "0.."}})
