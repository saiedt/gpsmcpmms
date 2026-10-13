"""A parameter of type "password" is write-only (since 0.46).

Its value is taken and never handed out again. The editor is given
SECRET_SET in its place -- "there is one" -- and what it sends back is read
accordingly: the stand-in unchanged means "leave it", anything else is a new
secret, the empty string clears it.

The module "vault" in conftest has a secret in every place one can stand: on
its own, behind the admin password, inside a group with a test of its own,
and in the records of a keyed list.
"""

import json

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode, SECRET_MARK, SECRET_SET

API = {"X-GPSMCPMMS-Api": "1"}
FACTORY = config_mgr.FACTORY_DEFAULT_PASSWD

SEED = {
    "key": "key-in-the-clear",
    "locked": "locked-in-the-clear",
    "login": {"user": "ada", "passwd": "login-in-the-clear"},
    "accounts": [{"name": "one", "secret": "first-in-the-clear"},
                 {"name": "two", "secret": "second-in-the-clear"},
                 {"name": "three", "secret": ""}],
}
CLEAR = ("key-in-the-clear", "locked-in-the-clear", "login-in-the-clear",
         "first-in-the-clear", "second-in-the-clear")


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    CvvNode.update_module(cfg, "vault", json.loads(json.dumps(SEED)))
    with cfg._flask_app.test_client() as c:
        yield c
    cfg._invalidate_session("test fixture done")


def _stored(path):
    return config_mgr.query(f"vault.{path}")[f"vault.{path}"]


def _open(client, admin=True):
    resp = client.get("/api/cvv_data",
                      query_string={"passwd": FACTORY} if admin else None)
    return resp.get_json(), resp.get_data(as_text=True)


def _save(client, token, value):
    return client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vault", "value": value})


def _vault(body):
    return body["cvv"]["vault"]["children"] if "cvv" in body \
        else body["vault"]["children"]


def _find_vault(body):
    """The dump of "vault", wherever the answer keeps the tree."""
    for candidate in (body, body.get("cvv") or {}, body.get("data") or {}):
        if isinstance(candidate, dict) and "vault" in candidate:
            return candidate["vault"]["children"]
    raise AssertionError(f"no 'vault' in the answer: {list(body)}")


# --------------------------------------------------------------------------
# Nothing is handed out
# --------------------------------------------------------------------------

def test_no_secret_reaches_the_editor_not_even_an_administrators(client):
    body, text = _open(client, admin=True)
    assert body["admin"]
    for secret in CLEAR:
        assert secret not in text
    assert body["secret_set"] == SECRET_SET


def test_the_editor_is_told_only_that_there_is_one(client):
    body, _ = _open(client, admin=True)
    vault = _find_vault(body)
    assert vault["key"]["value"] == SECRET_SET
    assert vault["locked"]["value"] == SECRET_SET
    assert vault["login"]["children"]["passwd"]["value"] == SECRET_SET
    # what is no secret stays what it is
    assert vault["login"]["children"]["user"]["value"] == "ada"
    members = vault["accounts"]["value"]
    assert [m["name"] for m in members] == ["one", "two", "three"]
    assert [m["secret"] for m in members] == [SECRET_SET, SECRET_SET, ""], \
        "a secret that is not set is not said to be"


def test_without_the_admin_password_the_same_holds(client):
    body, text = _open(client, admin=False)
    assert not body["admin"]
    for secret in CLEAR:
        assert secret not in text
    vault = _find_vault(body)
    assert vault["key"]["value"] == SECRET_SET
    assert "locked" not in vault, "a protected secret is not even named"


def test_the_application_still_reads_what_it_stored(client):
    # the withholding is the editor's; the module that owns the secret needs
    # it to present it to whoever it is for
    assert _stored("key") == "key-in-the-clear"
    assert _stored("login.passwd") == "login-in-the-clear"


# --------------------------------------------------------------------------
# What comes back
# --------------------------------------------------------------------------

def test_sent_back_as_it_came_nothing_changes(client):
    body, _ = _open(client)
    vault = _find_vault(body)
    # the whole module as an editor holds it, the stand-ins included
    resp = _save(client, body["token"], {
        "key": vault["key"]["value"],
        "locked": vault["locked"]["value"],
        "login": {"user": "ada",
                  "passwd": vault["login"]["children"]["passwd"]["value"]},
        "accounts": vault["accounts"]["value"],
    })
    assert resp.status_code == 200 and resp.get_json()["rejected"] == []
    assert _stored("key") == "key-in-the-clear"
    assert _stored("locked") == "locked-in-the-clear"
    assert _stored("login.passwd") == "login-in-the-clear"
    assert [m["secret"] for m in _stored("accounts")] == [
        "first-in-the-clear", "second-in-the-clear", ""]


def test_a_dotted_key_is_the_same_statement(client):
    token = _open(client)[0]["token"]
    _save(client, token, {"login.passwd": SECRET_SET, "login.user": "ben"})
    assert _stored("login.user") == "ben"
    assert _stored("login.passwd") == "login-in-the-clear"


def test_a_new_value_replaces_the_secret_and_the_empty_one_clears_it(client):
    token = _open(client)[0]["token"]
    _save(client, token, {"key": "a new key", "login": {"passwd": ""}})
    assert _stored("key") == "a new key"
    assert not _stored("login.passwd")

    body, text = _open(client)
    vault = _find_vault(body)
    assert "a new key" not in text
    assert vault["key"]["value"] == SECRET_SET
    assert not vault["login"]["children"]["passwd"]["value"]


def test_typed_behind_the_dots_is_what_was_typed(client):
    # the field showed the stand-in and somebody typed on after it
    token = _open(client)[0]["token"]
    _save(client, token, {"key": SECRET_SET + "typed"})
    assert _stored("key") == "typed"


def test_the_stand_in_is_never_stored(client):
    token = _open(client)[0]["token"]
    CvvNode.update_module(config_mgr, "vault", {"key": ""})
    # nothing stored, and the stand-in arrives all the same
    _save(client, token, {"key": SECRET_SET})
    assert not _stored("key")
    folder = CvvNode._module_dir("vault")
    import glob
    import os
    for path in glob.glob(os.path.join(folder, "*")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        assert SECRET_MARK not in text
        assert SECRET_MARK.encode("unicode_escape").decode("ascii") not in text


# --------------------------------------------------------------------------
# In the records of a list
# --------------------------------------------------------------------------

def test_a_member_keeps_its_secret_when_the_one_before_it_goes(client):
    body, _ = _open(client)
    members = _find_vault(body)["accounts"]["value"]
    # "one" is removed; "two" moves up to its place and must not inherit
    # what "one" had
    _save(client, body["token"], {"accounts": members[1:]})
    assert _stored("accounts") == [
        {"name": "two", "secret": "second-in-the-clear"},
        {"name": "three", "secret": ""}]


def test_members_in_another_order_keep_their_own(client):
    body, _ = _open(client)
    members = _find_vault(body)["accounts"]["value"]
    _save(client, body["token"], {"accounts": [members[1], members[0]]})
    assert _stored("accounts") == [
        {"name": "two", "secret": "second-in-the-clear"},
        {"name": "one", "secret": "first-in-the-clear"}]


def test_a_new_member_has_no_secret_to_keep(client):
    body, _ = _open(client)
    members = _find_vault(body)["accounts"]["value"]
    # a stand-in under a name nothing is stored for: there is nothing it
    # could stand for
    members.append({"name": "four", "secret": SECRET_SET})
    members.append({"name": "five", "secret": "typed for five"})
    _save(client, body["token"], {"accounts": members})
    by_name = {m["name"]: m["secret"] for m in _stored("accounts")}
    assert not by_name["four"]
    assert by_name["five"] == "typed for five"
    assert by_name["one"] == "first-in-the-clear"


# --------------------------------------------------------------------------
# A test of the form as it stands
# --------------------------------------------------------------------------

def test_a_test_function_is_given_the_secret_the_form_was_never_told(client):
    body, _ = _open(client)
    resp = client.post("/api/config/test",
                       headers={**API, "X-GPSMCPMMS-Token": body["token"]},
                       json={"path": "vault.login",
                             "value": {"user": "ada", "passwd": SECRET_SET}})
    assert resp.status_code == 200
    # the fixture's test function answers with the password it was handed
    assert resp.get_json()["result"] == "login-in-the-clear"


def test_and_what_was_typed_into_the_form_is_tested_as_typed(client):
    body, _ = _open(client)
    resp = client.post("/api/config/test",
                       headers={**API, "X-GPSMCPMMS-Token": body["token"]},
                       json={"path": "vault.login",
                             "value": {"user": "ada", "passwd": "not saved yet"}})
    assert resp.get_json()["result"] == "not saved yet"
    assert _stored("login.passwd") == "login-in-the-clear"
