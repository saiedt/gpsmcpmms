"""What an application tells a portal about itself (0.48.0): every finding,
and a checksum of what only an administrator may change."""

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvNode

KEY = b"kept on the device"
ADA = {"number": "0151", "name": "Ada", "installed": True}
BEN = {"number": "0152", "name": "Ben", "installed": False}


@pytest.fixture
def restored(setup_demo_environment):
    """Whatever a test stores is put back afterwards."""
    before = {m: config_mgr.query(m)[m] for m in ("vtest", "mplist")}
    yield
    for module, value in before.items():
        CvvNode.update_module(config_mgr, module, value)


def test_findings_are_every_module_s_as_an_administrator_sees_them(restored):
    config_mgr.update_status("vtest", [{"text": "Something to see.", "level": "warning",
                                        "path": "vtest.secret"}])
    try:
        found = config_mgr.findings()
        assert {"text": "Something to see.", "level": "warning",
                "path": "vtest.secret"} in found["vtest"]
    finally:
        config_mgr.update_status("vtest", None)


def test_the_digest_follows_protected_values_and_nothing_else(restored):
    first = config_mgr.protected_digest(KEY)
    assert len(first) == 64 and config_mgr.protected_digest(KEY) == first
    CvvNode.update_module(config_mgr, "vtest", {"n": 7})              # the household's
    assert config_mgr.protected_digest(KEY) == first
    CvvNode.update_module(config_mgr, "vtest", {"secret": 42})        # the administrator's
    assert config_mgr.protected_digest(KEY) != first


def test_a_record_with_its_own_protection_counts_and_another_does_not(restored):
    CvvNode.update_module(config_mgr, "mplist", {"people": [ADA, BEN]})
    first = config_mgr.protected_digest(KEY)
    CvvNode.update_module(config_mgr, "mplist",
                          {"people": [ADA, dict(BEN, name="Benjamin")]})
    assert config_mgr.protected_digest(KEY) == first
    CvvNode.update_module(config_mgr, "mplist",
                          {"people": [dict(ADA, name="Adele"), BEN]})
    assert config_mgr.protected_digest(KEY) != first


def test_the_digest_needs_its_key_and_depends_on_it(restored):
    assert config_mgr.protected_digest(b"other") != config_mgr.protected_digest(KEY)
    with pytest.raises(ValueError):
        config_mgr.protected_digest(b"")
