"""Protection that comes out of a record, and options that come from
outside a list (spec 4.4, 4.9.1).

Both rules are about lists whose members are records: one says that a record
may carry its own lock, the other that a member may ask a field beyond its
list what to offer. The module "mplist" in conftest declares both.
"""

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode

API = {"X-GPSMCPMMS-Api": "1"}

ADA = {"number": "0151", "name": "Ada", "installed": True}
BEN = {"number": "0152", "name": "Ben", "installed": False}


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c


def _seed(people):
    """The stored state, put there without a session: what the installer
    left behind is the starting point of every one of these tests."""
    CvvNode.update_module(config_mgr, "mplist", {"people": people})


def _people():
    return config_mgr.query("mplist.people")["mplist.people"]


def _save(client, people, token):
    return client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "mplist",
                             "value": {"people": people}})


def _fresh_token(client):
    return client.get("/api/cvv_data").get_json()["token"]


def _admin_token(client):
    from gpsmcpmms.config import ConfigManager
    body = client.get("/api/cvv_data?passwd="
                      + ConfigManager.FACTORY_DEFAULT_PASSWD).get_json()
    assert body["admin"]
    return body["token"]


# --------------------------------------------------------------------------
# What a session without the password may not do
# --------------------------------------------------------------------------

def test_protected_record_cannot_be_changed(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(ADA, name="Somebody else"), dict(BEN)],
                 _fresh_token(client))
    assert resp.status_code == 200
    assert "mplist.people.00" in resp.get_json()["rejected"]
    assert _people()[0]["name"] == "Ada"


def test_protected_record_cannot_be_removed(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(BEN)], _fresh_token(client))
    assert "mplist.people.00" in resp.get_json()["rejected"]
    assert {one["number"] for one in _people()} == {"0151", "0152"}


def test_protection_cannot_be_given(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(ADA), dict(BEN, installed=True)],
                 _fresh_token(client))
    assert "mplist.people.01.installed" in resp.get_json()["rejected"]
    assert _people()[1]["installed"] is False


def test_an_unprotected_record_stays_the_household_s_own(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(ADA), dict(BEN, name="Bea")],
                 _fresh_token(client))
    assert resp.get_json()["rejected"] == []
    assert _people()[1]["name"] == "Bea"


def test_a_new_record_is_still_allowed(client):
    _seed([dict(ADA)])
    resp = _save(client, [dict(ADA),
                          {"number": "0154", "name": "Dana",
                           "installed": False}],
                 _fresh_token(client))
    assert resp.get_json()["rejected"] == []
    assert len(_people()) == 2


# --------------------------------------------------------------------------
# ...and what the password makes possible
# --------------------------------------------------------------------------

def test_admin_may_change_a_protected_record(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(ADA, name="Ada B."), dict(BEN)],
                 _admin_token(client))
    assert resp.get_json()["rejected"] == []
    assert _people()[0]["name"] == "Ada B."


def test_admin_may_remove_and_may_protect(client):
    _seed([dict(ADA), dict(BEN)])
    resp = _save(client, [dict(BEN, installed=True)], _admin_token(client))
    assert resp.get_json()["rejected"] == []
    assert [one["number"] for one in _people()] == ["0152"]
    assert _people()[0]["installed"] is True


# --------------------------------------------------------------------------
# A member that asks past its own list
# --------------------------------------------------------------------------

def test_a_member_may_name_a_field_outside_its_list(setup_demo_environment):
    cfg = setup_demo_environment
    path = "mplist.teams._list_item_template.members._list_item_template"
    cons = CvvNode.get_node_constraints(cfg, path)
    assert cons is not None
    assert cons.get("one_of_for") == "^group"


def test_the_provider_answers_for_the_group(client):
    """The editor sends the group along; the endpoint hands it to the
    provider, and what comes back is that group's people."""
    token = _fresh_token(client)
    path = "mplist.teams._list_item_template.members._list_item_template"
    resp = client.get("/api/config/enum-options?path=" + path + '&arg="red"',
                      headers={**API, "X-GPSMCPMMS-Token": token})
    assert resp.status_code == 200
    assert set(resp.get_json()["values"]) == {"0151", "0153"}
