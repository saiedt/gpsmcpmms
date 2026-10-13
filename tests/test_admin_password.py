"""The administrator password is kept as a one-way hash (since 0.45).

What these tests hold on to: the store never carries the password in the
clear -- not in the checkpoint, not in the one before it, not in the journal --
and everything that used to compare against it still gives the same answer:
unlocking, the factory-password notice, taking a session over.

The device of the test session stands on the factory password, and other
tests unlock with it. So every test here that sets a password puts the
factory one back.
"""

import glob
import os

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode

API = {"X-GPSMCPMMS-Api": "1"}
# not ASCII on purpose: a password may be anything, and the comparison used
# to refuse text of this kind outright
OWN = "Sönnenhof-2026 ß"
FACTORY = config_mgr.FACTORY_DEFAULT_PASSWD


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c
    # whatever a test left behind: back to the factory password
    CvvNode.update_module(cfg, cfg.OWN_MODULE_ID, {"ui_passwd": FACTORY})
    cfg._factory_passwd_cache = None
    cfg._invalidate_session("test fixture done")


def _unlock(client, passwd):
    return client.get("/api/cvv_data", query_string={"passwd": passwd}).get_json()


def _set_password(client, token, new):
    return client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": config_mgr.OWN_MODULE_ID,
                             "value": {"ui_passwd": new}})


def _stored():
    key = f"{config_mgr.OWN_MODULE_ID}.ui_passwd"
    return config_mgr.query(key)[key]


def _store_files():
    """Everything the store keeps of the library's own module, as text."""
    folder = CvvNode._module_dir(config_mgr.OWN_MODULE_ID)
    found = {}
    for path in glob.glob(os.path.join(folder, "*")):
        with open(path, encoding="utf-8") as f:
            found[os.path.basename(path)] = f.read()
    return found


def test_a_hash_is_not_the_password_and_verifies_only_it():
    one = config_mgr._hash_passwd(OWN)
    another = config_mgr._hash_passwd(OWN)
    assert one.startswith(config_mgr.PASSWD_SCHEME + "$")
    assert OWN not in one
    # salted: the same password twice is two different stored values
    assert one != another
    iterations, salt, digest = config_mgr._parse_passwd_hash(one)
    assert iterations == config_mgr.PASSWD_ITERATIONS
    assert len(salt) == config_mgr.PASSWD_SALT_BYTES and len(digest) == 32


@pytest.mark.parametrize("not_a_hash", [
    None, "", OWN, FACTORY, "pbkdf2_sha256$x$AAAA$AAAA",
    "pbkdf2_sha256$1000$not base64$AAAA", "md5$1$AAAA$AAAA",
    "pbkdf2_sha256$0$AAAA$AAAA", "pbkdf2_sha256$1000$AAAA",
])
def test_what_is_not_a_hash_is_not_taken_for_one(not_a_hash):
    assert config_mgr._parse_passwd_hash(not_a_hash) is None


def test_a_new_password_reaches_the_store_only_as_a_hash(client):
    body = _unlock(client, FACTORY)
    assert body["admin"] and body["factory_default_passwd"]

    resp = _set_password(client, body["token"], OWN)
    assert resp.status_code == 200 and resp.get_json()["rejected"] == []

    stored = _stored()
    assert config_mgr._parse_passwd_hash(stored) is not None
    assert OWN not in stored
    files = _store_files()
    assert files, "the store keeps nothing of the library's own module"
    for name, text in files.items():
        assert OWN not in text, f"{name} carries the password in the clear"
        assert OWN.encode("unicode_escape").decode("ascii") not in text, name


def test_the_new_password_unlocks_and_the_old_one_no_longer_does(client):
    token = _unlock(client, FACTORY)["token"]
    _set_password(client, token, OWN)
    config_mgr._invalidate_session("the same test, now as somebody else")

    wrong = _unlock(client, FACTORY)
    assert wrong["wrong_passwd"] and not wrong["admin"]
    assert not wrong["factory_default_passwd"]
    config_mgr._invalidate_session("and once more")

    right = _unlock(client, OWN)
    assert right["admin"] and not right["wrong_passwd"]
    assert not right["factory_default_passwd"]


def test_the_password_is_never_handed_out(client):
    token = _unlock(client, FACTORY)["token"]
    _set_password(client, token, OWN)
    body = client.get("/api/cvv_data",
                      headers={"X-GPSMCPMMS-Token": token}).get_json()
    assert body["admin"]
    text = client.get("/api/cvv_data",
                      headers={"X-GPSMCPMMS-Token": token}).get_data(as_text=True)
    assert OWN not in text
    assert config_mgr.PASSWD_SCHEME not in text, \
        "the hash has no business in the editor either"


def test_taking_a_session_over_asks_for_the_same_password(client):
    token = _unlock(client, FACTORY)["token"]
    _set_password(client, token, OWN)

    refused = client.post("/api/session/takeover", headers=API,
                          json={"passwd": FACTORY})
    assert refused.status_code == 403
    taken = client.post("/api/session/takeover", headers=API,
                        json={"passwd": OWN})
    assert taken.status_code == 200


def test_the_factory_password_set_again_is_noticed_again(client):
    token = _unlock(client, FACTORY)["token"]
    _set_password(client, token, OWN)
    assert not config_mgr._is_factory_passwd()

    _set_password(client, token, FACTORY)
    # stored as a hash like any other, and recognised all the same
    assert config_mgr._parse_passwd_hash(_stored()) is not None
    assert config_mgr._is_factory_passwd()
    config_mgr._invalidate_session("as somebody new")
    assert _unlock(client, FACTORY)["factory_default_passwd"]


def test_a_password_left_in_the_clear_is_sealed_with_both_checkpoints(client):
    # what a release before 0.45 left behind: the password as it was typed,
    # put there past the door that would have hashed it
    CvvNode.update_module(config_mgr, config_mgr.OWN_MODULE_ID,
                          {"ui_passwd": OWN})
    config_mgr._factory_passwd_cache = None
    assert _stored() == OWN
    # still the password until it is sealed
    assert config_mgr._passwd_matches(OWN)

    assert config_mgr._seal_stored_ui_passwd() is True

    assert config_mgr._parse_passwd_hash(_stored()) is not None
    assert config_mgr._passwd_matches(OWN)
    assert not config_mgr._passwd_matches(FACTORY)
    for name, text in _store_files().items():
        assert OWN not in text, f"{name} still carries the password"
        assert OWN.encode("unicode_escape").decode("ascii") not in text, name
    # and a second look finds nothing left to do
    assert config_mgr._seal_stored_ui_passwd() is False


def test_the_factory_default_is_left_as_it_is(client):
    # no password of the device's own: nothing to seal, and nothing written
    assert config_mgr._seal_stored_ui_passwd() is False
    assert config_mgr._is_factory_passwd()
