"""Validation / constraint enforcement — the core value of the library."""

import pytest

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


# --------------------------------------------------------------------------
# A 'file' parameter holds a bare name, and a declared pattern (spec 2.1)
# --------------------------------------------------------------------------

def _file_param(cfg, module_id, file_dir, **decl):
    """Registers a module whose one parameter, `f`, is a file. Every test
    takes an id of its own: a module id is spent the moment it is used."""
    funcs = {decl["values"]: lambda: {}} if "values" in decl else None
    cfg.register_params(
        module_id=module_id, module_label="Files",
        param_dict={"f": {"type": "file", "label": "File",
                          "file_dir": str(file_dir), **decl}},
        callback=lambda value: None, func_dict=funcs)


def _set_file(cfg, module_id, name):
    return CvvNode.update_module(cfg, module_id, {"f": name})[0]


def test_a_file_parameter_needs_no_pattern(setup_demo_environment, tmp_path):
    # bound_to is optional, and yet leaving it out ended the registration:
    # "Unknown simple type specification file."
    cfg = setup_demo_environment
    _file_param(cfg, "fbare", tmp_path)
    assert _set_file(cfg, "fbare", "notes.txt") == []
    # without a pattern the name still may not leave the directory
    assert _set_file(cfg, "fbare", "../notes.txt") == ["fbare.f"]
    assert cfg.query("fbare.f")["fbare.f"] == "notes.txt"


@pytest.mark.parametrize("module_id, provider",
                         [("fwav", None), ("fwavlist", "list_tones")])
def test_a_declared_pattern_holds_for_every_value(setup_demo_environment,
                                                  tmp_path, module_id,
                                                  provider):
    # Only the upload applied the pattern. A value set any other way met a
    # check that looked at the type alone, so "x.exe" went through the API
    # into a parameter declared "wav only". A provider leaves open which
    # files are on offer, not what their names may look like.
    cfg = setup_demo_environment
    decl = {"bound_to": r".+\.wav"}
    if provider:
        decl["values"] = provider
    _file_param(cfg, module_id, tmp_path, **decl)
    path = f"{module_id}.f"
    assert _set_file(cfg, module_id, "bell.wav") == []
    assert _set_file(cfg, module_id, "x.exe") == [path]
    # a name the pattern admits still may not leave the directory
    assert _set_file(cfg, module_id, "../bell.wav") == [path]
    assert cfg.query(path)[path] == "bell.wav"


# --------------------------------------------------------------------------
# A release may tighten a bound under values that are already stored
# --------------------------------------------------------------------------

def test_a_member_value_outside_its_bound_is_dropped_and_not_fatal(
        setup_demo_environment):
    # The member takes its value while its node is being built, and there
    # every value used to count as a declaration: one stored second outside a
    # bound the release had just narrowed raised CvvLoadError, the module did
    # not load, and the editor that could have repaired it lives in the same
    # process. The value is data and is dropped like any other refused one.
    cfg = setup_demo_environment
    rejected, _ = CvvNode.update_module(
            cfg, "blist", {"entries": [{"name": "A", "seconds": 40}]})
    assert rejected                                # 40 is outside 10..20
    entries = cfg.query("blist.entries")["blist.entries"]
    assert len(entries) == 1                       # ...the member stays,
    assert entries[0]["name"] == "A"               # everything else intact,
    assert entries[0]["seconds"] == 16             # the declaration's own value


def test_a_member_keeps_what_the_declaration_still_knows(
        setup_demo_environment):
    # The same for a property a release has removed: the stored record names
    # something the declaration no longer has, which was fatal through the
    # unknown-key check.
    cfg = setup_demo_environment
    rejected, _ = CvvNode.update_module(
            cfg, "blist",
            {"entries": [{"name": "B", "seconds": 12, "gone": "x"}]})
    assert rejected
    entries = cfg.query("blist.entries")["blist.entries"]
    assert entries == [{"name": "B", "seconds": 12}]
