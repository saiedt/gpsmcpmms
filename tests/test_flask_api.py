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
    cfg._invalidate_session()
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
