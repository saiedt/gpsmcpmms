"""Hints on the things that are not plain fields (spec 4.9.5).

A hint asserts something about the present, so it is fetched rather than
shipped, and the schema says only that there is one to fetch. That works the
same for a group and for a list as for a field -- and the editor dropped both
for a while, rendering hints in one branch of renderNode() and forgetting them
in the two above it. The declaration was right, the server answered, and
nothing appeared. These tests hold the half of that contract which can be
tested here: what the schema promises the editor, and what the editor gets
when it asks.
"""

import json

import pytest

from gpsmcpmms.cvv_tree import CvvNode


TYPES = {
    "member_t": {"inner": {"label": "Inner", "type": "string"}},
    "member_list": {"list_member": {"type": "member_t"}, "list_size": "0.."},
}
PARAMS = {
    "field": {"label": "Field", "type": "string", "hint": "say_now"},
    "group": {"label": "Group", "type": "member_t", "hint": "say_now"},
    "list": {"label": "List", "type": "member_list", "hint": "say_now"},
    "spelt_out": {"label": "Spelt out", "type": "string",
                  "hint": "This one says it itself."},
}


@pytest.fixture(scope="module")
def mgr(setup_demo_environment):
    """Registered once: the CVV tree is one tree per process, and a module id
    is spent the moment it is used."""
    cfg = setup_demo_environment
    cfg.register_params(module_id="hinted", module_label="Hinted",
                        param_dict=PARAMS, type_dict=TYPES,
                        callback=lambda value: None,
                        func_dict={"say_now": lambda lang: "it is now"})
    return cfg


def _nodes(mgr):
    """The module's own parameters: a module is itself a node, and they hang
    under its children."""
    return json.loads(CvvNode.get_cvv_json_dump(mgr))["hinted"]["children"]


def _ui(mgr, name):
    return _nodes(mgr)[name]["ui"]


@pytest.mark.parametrize("name", ["field", "group", "list"])
def test_the_schema_promises_a_hint_wherever_one_was_declared(mgr, name):
    # True and not the provider's name: which function produces the sentence
    # is nobody's business outside the device, and the editor only needs to
    # know that asking is worth its while.
    assert _ui(mgr, name).get("hint") is True


def test_a_group_and_a_list_are_still_a_group_and_a_list(mgr):
    # The hint rides on the container, not on a child invented to carry it:
    # that is what made the editor's field-only branch miss it.
    nodes = _nodes(mgr)
    assert "children" in nodes["group"]
    assert "item_template" in nodes["list"]


def test_a_hint_written_out_travels_as_itself(mgr):
    # Nothing to fetch: it is a sentence, so it goes in the schema and becomes
    # a translation key like any other label.
    assert _ui(mgr, "spelt_out")["hint"] == "This one says it itself."


@pytest.mark.parametrize("name", ["field", "group", "list"])
def test_the_provider_is_reachable_by_the_node_s_own_path(mgr, name):
    # What /api/config/hint does with the path the editor sends. A container
    # resolves the same way a leaf does, which is why the fix was the editor's
    # alone.
    assert CvvNode.get_hint(mgr, f"hinted.{name}") == "say_now"
