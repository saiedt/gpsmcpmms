"""Validation / constraint enforcement — the core value of the library."""

from gpsmcpmms.cvv_tree import CvvNode


def test_in_bounds_value_accepted(setup_demo_environment):
    cfg = setup_demo_environment
    rejected, _ = CvvNode.update_module(cfg, "vtest", {"n": 7})
    assert rejected == []
    assert cfg.query("vtest.n")["vtest.n"] == 7


def test_out_of_bounds_value_rejected(setup_demo_environment):
    cfg = setup_demo_environment
    CvvNode.update_module(cfg, "vtest", {"n": 4})          # known good value
    rejected, _ = CvvNode.update_module(cfg, "vtest", {"n": 99})
    assert rejected                                        # 99 is outside 1..10
    assert cfg.query("vtest.n")["vtest.n"] == 4            # left unchanged


def test_wrong_type_value_rejected(setup_demo_environment):
    cfg = setup_demo_environment
    CvvNode.update_module(cfg, "vtest", {"n": 6})          # known good value
    rejected, _ = CvvNode.update_module(cfg, "vtest", {"n": "not-an-int"})
    assert rejected
    assert cfg.query("vtest.n")["vtest.n"] == 6            # left unchanged


# --------------------------------------------------------------------------
# A member of a keyed list must be known by its keys (spec 4.9.2)
# --------------------------------------------------------------------------

# Registered by conftest: "klist" carries a list of {rfid, sid, note} whose
# first two properties are its list_keys.
def _cards(cfg):
    return cfg


def _set(cfg, members):
    return CvvNode.update_module(cfg, "klist", {"cards": members})[0]


def test_a_member_with_every_key_filled_is_kept(setup_demo_environment):
    cfg = _cards(setup_demo_environment)
    assert _set(cfg, [{"rfid": "A", "sid": "s1"}]) == []
    assert cfg.query("klist.cards")["klist.cards"] == [{"rfid": "A",
                                                        "sid": "s1",
                                                        "note": None}]


def test_a_member_may_leave_everything_but_its_keys_open(setup_demo_environment):
    # The rule is about identity, not about being finished. Whoever adds a
    # card has to say which card it is; nothing says the note has to be
    # written in the same sitting.
    cfg = _cards(setup_demo_environment)
    assert _set(cfg, [{"rfid": "A", "sid": "s1", "note": None}]) == []
    assert cfg.query("klist.cards")["klist.cards"][0]["note"] is None


def test_a_member_missing_a_key_is_refused(setup_demo_environment):
    cfg = _cards(setup_demo_environment)
    _set(cfg, [{"rfid": "A", "sid": "s1"}])
    rejected = _set(cfg, [{"rfid": "A", "sid": "s1"},
                          {"rfid": None, "sid": "s2"}])
    assert rejected == ["klist.cards"]
    assert cfg.query("klist.cards")["klist.cards"] == [{"rfid": "A",
                                                        "sid": "s1",
                                                        "note": None}]


def test_an_emptied_key_counts_as_missing(setup_demo_environment):
    # The one that went unnoticed. "" is not None to Python, but it is to a
    # reader -- and it is what an editor leaves behind when a field is
    # cleared, so this was the shape a lost card id actually had.
    cfg = _cards(setup_demo_environment)
    _set(cfg, [{"rfid": "A", "sid": "s1"}])
    rejected = _set(cfg, [{"rfid": "A", "sid": "s1"},
                          {"rfid": "", "sid": "s2"}])
    assert rejected == ["klist.cards"]
    assert len(cfg.query("klist.cards")["klist.cards"]) == 1
