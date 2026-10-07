import json
import pytest
from gpsmcpmms.cvv_tree import CvvNode, CvvError


def test_unauthorized_cvv_access():
    """Verify CvvNode rejects queries from unauthorized holder objects."""
    unauthorized_holder = object()

    with pytest.raises(CvvError):
        CvvNode.get_cvv_json_dump(unauthorized_holder)


def test_authorized_cvv_query(setup_demo_environment):
    """Verify CvvNode queries succeed when called via authorized config_mgr."""
    cfg_mgr = setup_demo_environment

    # Query registered modules via authorized holder
    assert CvvNode.query(cfg_mgr, "log") is not None
    assert CvvNode.query(cfg_mgr, "led") is not None
    assert CvvNode.query(cfg_mgr, "sip") is not None


def test_cvv_json_dump(setup_demo_environment):
    """Verify get_cvv_json_dump returns JSON encoding the registered module keys."""
    cfg_mgr = setup_demo_environment
    data = json.loads(CvvNode.get_cvv_json_dump(cfg_mgr))

    assert isinstance(data, dict)
    assert "log" in data
    assert "led" in data
    assert "sip" in data


# --------------------------------------------------------------------------
# What a declaration says about how a thing is shown
# --------------------------------------------------------------------------

def test_a_display_hint_reaches_the_editor_as_it_is(setup_demo_environment):
    from gpsmcpmms import config_mgr
    hint = {"summary": {"title": "name", "chips": "tags"}, "filter": "tags",
            "fold": True}
    config_mgr.register_params(
        module_id="shown", module_label="Shown",
        param_dict={"people": {
            "label": "People", "type": "person_list",
            "display": hint}},
        type_dict={"person_list": {
            "list_member": {"type": "person"}, "list_size": "0.."},
            "person": {"name": {"type": "string", "label": "Name"},
                       "tags": {"type": "tag_list", "label": "Tags"}},
            "tag_list": {"list_member": {"type": "string"}, "list_size": "0.."}},
        callback=lambda value: None)
    data = json.loads(CvvNode.get_cvv_json_dump(config_mgr))
    node = data["shown"]["children"]["people"]
    assert node["ui"]["display"] == hint
    # the dump is a copy: what the module keeps is not the editor's to bend
    hint["fold"] = False
    data = json.loads(CvvNode.get_cvv_json_dump(config_mgr))
    assert data["shown"]["children"]["people"]["ui"]["display"]["fold"] is True


def test_a_display_hint_that_is_not_a_dict_is_refused(setup_demo_environment):
    from gpsmcpmms import config_mgr
    with pytest.raises(Exception):
        config_mgr.register_params(
            module_id="misshown", module_label="Misshown",
            param_dict={"thing": {"type": "string", "label": "Thing",
                                  "display": "big"}},
            callback=lambda value: None)
