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
