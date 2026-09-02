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
