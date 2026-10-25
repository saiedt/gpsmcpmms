"""A relevance rule on a protected sibling is settled for a session
without the password (since 0.46.2).

The session is not told the sibling's value -- protection takes the
parameter out of its tree -- but the value is what decides whether the
child is shown. Settled by the backend, the child it governs arrives
without the rule where the rule holds, and not at all where it does not.
A rule on an open sibling stays as it is: the editor judges it live.

The module "where" in conftest: a protected country, one place field per
country, and a detail switched by an open boolean.
"""

import json

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode

FACTORY = config_mgr.FACTORY_DEFAULT_PASSWD


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c
    cfg._invalidate_session("test fixture done")


def _where(client, admin):
    resp = client.get("/api/cvv_data",
                      query_string={"passwd": FACTORY} if admin else None)
    body = resp.get_json()
    tree = body["cvv"] if "cvv" in body else body
    return tree["where"]


def _set_country(code):
    cfg = config_mgr
    CvvNode.update_module(cfg, "where", {"country": code})


def test_viewer_gets_the_relevant_field_without_its_rule(client):
    _set_country("DE")
    where = _where(client, admin=False)
    children = where["children"]
    assert "country" not in children, "protected, so withheld"
    assert "place_de" in children, "the field the country shows"
    assert "place_at" not in children, "the field another country would show"
    rules = where.get("relevance") or {}
    assert "place_de" not in rules and "place_at" not in rules
    # the rule on the open sibling is still the editor's to judge
    assert "detail" in children
    assert rules.get("detail", {}).get("child_key") == "detailed"
    assert rules["detail"]["op"] == "=="


def test_viewer_follows_the_country(client):
    _set_country("AT")
    try:
        children = _where(client, admin=False)["children"]
        assert "place_at" in children and "place_de" not in children
    finally:
        _set_country("DE")


def test_admin_gets_everything_with_the_rules(client):
    _set_country("DE")
    where = _where(client, admin=True)
    children = where["children"]
    assert {"country", "place_de", "place_at", "detailed", "detail"} <= set(children)
    assert where["relevance"]["place_de"] == {"child_key": "country", "op": "==", "value": "DE"}
    assert where["relevance"]["place_at"] == {"child_key": "country", "op": "==", "value": "AT"}


def test_the_dump_itself_is_not_changed(client):
    """What the viewer is given is a copy: the next administrator sees
    the rules again."""
    _set_country("DE")
    _where(client, admin=False)
    cfg = config_mgr
    cfg._invalidate_session("between the two sessions of the test")
    where = _where(client, admin=True)
    assert "place_at" in where["children"] and "place_at" in where["relevance"]
    json.dumps(where)
