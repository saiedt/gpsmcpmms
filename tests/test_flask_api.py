"""REST API reachability plus the security contract (spec 4.4 / 4.8)."""

import pytest
from gpsmcpmms import config_mgr

API = {"X-GPSMCPMMS-Api": "1"}


@pytest.fixture
def client(setup_demo_environment):
    """Flask test client against the initialized config_mgr, with a fresh
    (invalidated) exclusive session so each test can obtain its own token."""
    cfg = setup_demo_environment
    # Build the Flask app and register its routes without serving it.
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c


def _fresh_token(client):
    return client.get("/api/cvv_data").get_json()["token"]


def test_cvv_data_ok_and_hides_config_module(client):
    """GET /api/cvv_data is 200 JSON, exposes registered modules, and never
    leaks the internal `config` module (regression for the suppression)."""
    resp = client.get("/api/cvv_data")
    assert resp.status_code == 200
    assert resp.is_json
    cvv = resp.get_json()["cvv"]
    assert "config" not in cvv                       # internal module stays hidden
    assert {"log", "led", "sip", "vtest"} <= set(cvv)


def test_update_requires_csrf_header(client):
    """POST without the X-GPSMCPMMS-Api header is refused (anti-CSRF)."""
    resp = client.post("/api/config/update",
                       json={"module": "vtest", "value": {"n": 3}})
    assert resp.status_code == 403


def test_update_requires_valid_token(client):
    """POST with the header but no/invalid session token is unauthorized."""
    resp = client.post("/api/config/update", headers=API,
                       json={"module": "vtest", "value": {"n": 3}})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_token"


def test_valid_update_round_trips(client):
    """A properly authorized update to a non-protected param is applied."""
    token = _fresh_token(client)
    resp = client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest", "value": {"n": 9}})
    assert resp.status_code == 200
    assert resp.get_json()["rejected"] == []
    assert config_mgr.query("vtest.n")["vtest.n"] == 9


def test_protected_param_stripped_for_non_admin(client):
    """Without admin, an update to a protected param is stripped, not applied."""
    token = _fresh_token(client)
    resp = client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest", "value": {"secret": 42}})
    assert resp.status_code == 200
    assert resp.get_json()["rejected"]                       # secret rejected
    assert config_mgr.query("vtest.secret")["vtest.secret"] == 0   # unchanged


# --------------------------------------------------------------------------
# Bringing a retired module's parameters back (/api/config/revive)
# --------------------------------------------------------------------------

def _admin_token(client):
    """A session that has passed the password, which is what the button needs:
    only an administrator sees a resting module at all."""
    from gpsmcpmms.config import ConfigManager
    resp = client.get("/api/cvv_data?passwd="
                      + ConfigManager.FACTORY_DEFAULT_PASSWD)
    body = resp.get_json()
    assert body["admin"], "the fixture's device is not on the factory password"
    return body["token"]


def test_revive_needs_the_csrf_header(client):
    assert client.post("/api/config/revive",
                       json={"module": "napping"}).status_code == 403


def test_revive_needs_admin(client):
    token = _fresh_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "napping"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "admin_required"


def test_revive_of_a_module_that_is_not_resting_is_a_404(client):
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest"})
    assert resp.status_code == 404


def test_revive_calls_the_module_back_and_hands_out_a_new_token(client):
    called = []
    config_mgr.register_params(
        module_id="napping", module_label="Napping",
        param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
        callback=lambda value: None)

    def wake_up():
        called.append(True)
        config_mgr.register_params(
            module_id="napping", module_label="Napping",
            param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
            callback=lambda value: None)

    config_mgr.discard_module("napping", revive=wake_up)
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "napping"})
    assert resp.status_code == 200
    assert called == [True]
    # Registering ends the editing session, so a new token comes back with the
    # answer; without it the administrator would be sent to the password
    # prompt for having pressed a button.
    assert resp.get_json()["token"]
    assert "napping" not in config_mgr._dormant


def test_a_way_back_that_does_not_register_is_reported_as_a_failure(client):
    config_mgr.register_params(
        module_id="dozing", module_label="Dozing",
        param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
        callback=lambda value: None)
    config_mgr.discard_module("dozing", revive=lambda: None)
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "dozing"})
    # It ran without raising and changed nothing. Calling that a success would
    # send the editor looking for a panel that is not there.
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "revive_failed"
