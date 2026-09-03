"""What a module says about itself, on its way to the editor's banner.

The status rides back on the callback every module already has. That is the
whole point of the design: there is no second place to keep in step, and so no
second place to forget. These tests hold the consequences of that choice --
that a callback saying nothing means nothing to report, that the newest answer
replaces the last one, and that a module which gives up its parameters takes
its banner with it rather than leaving one nobody can reach.
"""

import pytest

from gpsmcpmms.config import ConfigManager


PARAMS = {"greeting": {"label": "Greeting", "type": "string"}}


@pytest.fixture
def mgr(tmp_path, monkeypatch):
    monkeypatch.setenv("GPSMCPMMS_CVV_DIR", str(tmp_path / "cvv"))
    return ConfigManager()


def _register(mgr, module_id, callback):
    mgr.register_params(module_id=module_id, module_label="Test module",
                        param_dict=PARAMS, callback=callback)


def _messages(mgr, module_id):
    return mgr._module_status_report().get(module_id)


def test_a_silent_callback_reports_nothing(mgr):
    # Every callback written before the status existed returns None without
    # meaning to. None of them may start showing a banner because of it.
    _register(mgr, "quiet", lambda value: None)
    assert _messages(mgr, "quiet") is None


def test_one_finding_and_several_are_both_allowed(mgr):
    _register(mgr, "one", lambda value: "Something is amiss.")
    assert _messages(mgr, "one") == ["Something is amiss."]

    _register(mgr, "many", lambda value: ["First thing.", "Second thing."])
    assert _messages(mgr, "many") == ["First thing.", "Second thing."]


def test_a_finding_is_the_whole_line(mgr):
    # No module name is put in front of it. What a finding is about is often a
    # group inside a module -- service cards, say, rather than "Application" --
    # and a heading composed here would be right for some and wrong for the
    # rest.
    _register(mgr, "whole", lambda value: "Service cards: one points nowhere.")
    assert _messages(mgr, "whole") == ["Service cards: one points nowhere."]


def test_a_finding_becomes_a_translation_key(mgr):
    # Otherwise it reaches the reader in the language its module happened to be
    # written in, which for seven readers out of eight is the wrong one.
    _register(mgr, "keyed", lambda value: "Something is amiss.")
    assert "Something is amiss." in mgr._active_xlation_keys


def test_the_latest_answer_replaces_the_last(mgr):
    reports = ["Something is amiss."]
    _register(mgr, "changing", lambda value: reports[0])
    assert _messages(mgr, "changing") == ["Something is amiss."]

    # what a module says once must not outlive the reason for saying it
    reports[0] = None
    mgr._apply_module_update("changing", {"greeting": "hello"})
    assert _messages(mgr, "changing") is None


def test_giving_up_the_parameters_takes_the_status_along(mgr):
    # tts retires itself once everything is voiced. A banner outliving its
    # panel could not be acted on, and could not be got rid of either.
    _register(mgr, "leaving", lambda value: "Something is amiss.")
    assert _messages(mgr, "leaving") == ["Something is amiss."]

    mgr.discard_module("leaving")
    assert _messages(mgr, "leaving") is None


def test_a_callback_returning_something_else_is_refused(mgr):
    # Loudly, and at registration: a status that is neither a string nor a list
    # of them would otherwise show up as whatever repr() makes of it.
    with pytest.raises(ValueError):
        _register(mgr, "wrong", lambda value: 42)


def test_a_module_may_report_between_callbacks(mgr):
    # The callback fires at the start of a run and then only if somebody
    # edits that module's configuration, while a run on an appliance lasts
    # months. What a module learns in between -- a server that does not answer
    # a test button -- would otherwise have nowhere to go until the next boot.
    _register(mgr, "later", lambda value: None)
    assert _messages(mgr, "later") is None

    mgr.update_status("later", "The server cannot be reached.")
    assert _messages(mgr, "later") == ["The server cannot be reached."]

    mgr.update_status("later", None)
    assert _messages(mgr, "later") is None


def test_reporting_replaces_rather_than_adds(mgr):
    # Both doors say the same kind of thing: everything the module currently
    # has to say. Otherwise a module would have to remember which finding it
    # announced through which, and how to take just that one back.
    _register(mgr, "both-doors", lambda value: "First thing.")
    mgr.update_status("both-doors", ["Second thing.", "Third thing."])
    assert _messages(mgr, "both-doors") == ["Second thing.", "Third thing."]


def test_an_unregistered_module_cannot_report(mgr):
    # A typo would otherwise raise a banner belonging to nothing, which no
    # later call could take down again.
    with pytest.raises(ValueError):
        mgr.update_status("never-registered", "Something is amiss.")


# --------------------------------------------------------------------------
# Retiring without disappearing (discard_module's `revive`)
# --------------------------------------------------------------------------

def test_a_module_that_left_a_way_back_keeps_its_findings(mgr):
    # The whole point of the argument. tts retires once everything is voiced,
    # and a recording can go out of date long afterwards -- with no way back
    # the finding had nowhere to appear, and the only trace was a line in a
    # log nobody reads on a shipped device.
    _register(mgr, "kept", lambda value: "Something is amiss.")
    mgr.discard_module("kept", revive=lambda: None)
    assert _messages(mgr, "kept") == ["Something is amiss."]


def test_a_resting_module_may_still_report(mgr):
    _register(mgr, "late-word", lambda value: None)
    mgr.discard_module("late-word", revive=lambda: None)

    mgr.update_status("late-word", "Found it later.")
    assert _messages(mgr, "late-word") == ["Found it later."]


def test_without_a_way_back_nothing_is_kept(mgr):
    # Unchanged behaviour for every existing caller: no revive, no trace.
    _register(mgr, "gone", lambda value: "Something is amiss.")
    mgr.discard_module("gone")
    assert _messages(mgr, "gone") is None
    with pytest.raises(ValueError):
        mgr.update_status("gone", "Anything at all.")


def test_the_editor_is_told_which_modules_are_resting(mgr):
    # By their heading alone: the tree node went with the parameters, so there
    # is nothing else left to draw them from.
    _register(mgr, "listed", lambda value: None)
    assert "listed" not in mgr._dormant
    mgr.discard_module("listed", revive=lambda: None)
    assert mgr._dormant["listed"]["label"] == "Test module"


def test_registering_again_is_the_way_out_of_resting(mgr):
    # What the button does, by way of the module's own callable. Nothing else
    # clears the standing, so a module that only pretended to register would
    # leave the editor waiting for a panel that never comes -- which is why
    # the endpoint checks this and calls it a failure.
    _register(mgr, "returning", lambda value: None)
    mgr.discard_module("returning", revive=lambda: None)
    _register(mgr, "returning", lambda value: None)
    assert "returning" not in mgr._dormant


def test_a_way_back_that_is_not_callable_is_refused(mgr):
    _register(mgr, "bad-way-back", lambda value: None)
    with pytest.raises(ValueError):
        mgr.discard_module("bad-way-back", revive="press here")
