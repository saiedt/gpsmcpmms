import pytest
from gpsmcpmms.cvv_tree import CvvNode


def test_unauthorized_cvv_access():
    """Verify CvvNode rejects queries from unauthorized holder objects."""
    unauthorized_holder = object()
    
    with pytest.raises((ValueError, PermissionError, TypeError, KeyError)):
        CvvNode.get_cvv_json_dump(unauthorized_holder)


def test_authorized_cvv_query(setup_demo_environment):
    """Verify CvvNode queries succeed when called via authorized config_mgr."""
    cfg_mgr = setup_demo_environment
    
    # Query registered modules via authorized holder
    assert CvvNode.query(cfg_mgr, "log") is not None
    assert CvvNode.query(cfg_mgr, "led") is not None
    assert CvvNode.query(cfg_mgr, "sip") is not None


def test_cvv_json_dump(setup_demo_environment):
    """Verify get_cvv_json_dump returns a populated dict containing registered module keys."""
    cfg_mgr = setup_demo_environment
    dump = CvvNode.get_cvv_json_dump(cfg_mgr)

    assert isinstance(dump, (dict, list))
    dump_str = str(dump)
    assert "log" in dump_str
    assert "led" in dump_str
    assert "sip" in dump_str
