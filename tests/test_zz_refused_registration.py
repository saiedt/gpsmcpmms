"""A refused registration leaves nothing behind.

A declaration is refused halfway through being taken in: by then the module
has written its id, its callback and the keys of its labels into the manager,
and its node hangs in the tree with children that were never finished. All of
that used to stay. The next thing to walk the tree -- every answer to the
editor -- then failed, for a mistake in one module's declaration; and the
module's id counted as taken, so the corrected declaration was refused as
well.

It showed in the tests before anywhere else: test_refreshable.py registers
declarations that must be refused, and every file that ran after it and asked
for the editor's data failed. The files happened to be in an order in which
none did. This file is named to run last, after everything that refuses.
"""

import os
import time

import pytest

from gpsmcpmms import config_mgr
from gpsmcpmms.cvv_tree import CvvError, CvvNode

API = {"X-GPSMCPMMS-Api": "1"}

# refused by the tree, while it builds the module
NOT_AN_ENUM = {"label": "A name nobody can ask for again", "type": "string",
               "refreshable": True}
# refused by the manager's own checks, before the tree is asked
DEAF = {"label": "A device nobody can be told about", "type": "enum",
        "values": "get", "refreshable": True}
SOUND = {"label": "A sound declaration", "type": "int", "default_val": 3}


def _nobody_to_tell():
    return {"aa": {"label": "Known", "verbatim": True}}


def _register(module_id, decl, funcs=None):
    config_mgr.register_params(
            module_id=module_id, module_label=f"Label of {module_id}",
            module_tooltip=f"Tooltip of {module_id}",
            param_dict={"field": decl}, callback=lambda value: None,
            func_dict=funcs)


def _refuse(module_id, decl=NOT_AN_ENUM, funcs=None):
    with pytest.raises((CvvError, ValueError)):
        _register(module_id, decl, funcs)


@pytest.fixture
def client(setup_demo_environment):
    cfg = setup_demo_environment
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c
    cfg._invalidate_session("test fixture done")


@pytest.mark.parametrize("module_id, decl, funcs", [
    ("refused-by-the-tree", NOT_AN_ENUM, None),
    ("refused-by-the-manager", DEAF, {"get": _nobody_to_tell}),
])
def test_the_editor_goes_on_working(client, module_id, decl, funcs):
    _refuse(module_id, decl, funcs)
    resp = client.get("/api/cvv_data")
    assert resp.status_code == 200
    assert module_id not in resp.get_data(as_text=True)
    # and the schema, which walks the declarations
    assert client.get("/api/schema").status_code == 200


@pytest.mark.parametrize("module_id, decl, funcs", [
    ("debris-of-the-tree", NOT_AN_ENUM, None),
    ("debris-of-the-manager", DEAF, {"get": _nobody_to_tell}),
])
def test_nothing_of_it_stays_behind(setup_demo_environment, module_id, decl,
                                    funcs):
    mgr = setup_demo_environment
    keys_before = set(mgr._active_xlation_keys)
    kinds_before = {key: set(kind) for key, kind in mgr._xlation_kinds.items()}

    _refuse(module_id, decl, funcs)

    assert module_id not in CvvNode._root_instance._children
    assert module_id not in CvvNode._module_locks
    assert module_id not in CvvNode._type_context
    for registry in (mgr._callback_registry, mgr._func_registry,
                     mgr._state_funcs, mgr._module_labels, mgr._dormant):
        assert module_id not in registry
    # the labels of a module that was not registered are nobody's to translate
    assert set(mgr._active_xlation_keys) == keys_before
    assert mgr._xlation_kinds == kinds_before


def test_the_declaration_put_right_is_accepted_under_the_same_id(client):
    module_id = "second-attempt"
    _refuse(module_id)
    _register(module_id, SOUND)
    assert config_mgr.query(f"{module_id}.field")[f"{module_id}.field"] == 3
    assert module_id in client.get("/api/cvv_data").get_data(as_text=True)


def test_what_an_earlier_run_stored_for_it_is_not_touched(setup_demo_environment):
    # A release with a mistake in a declaration must not cost the device the
    # values it holds for that module: they belong to the declaration that
    # will be accepted, and that one is a correction away.
    module_id = "kept-on-disk"
    folder = CvvNode._module_dir(module_id)
    os.makedirs(folder, exist_ok=True)
    dump = os.path.join(folder, CvvNode._dump_file_name)
    with open(dump, "w", encoding="utf-8") as f:
        f.write(repr({"saved_at": time.time(), "value": {"field": 8}}))
    stored = open(dump, encoding="utf-8").read()

    _refuse(module_id)

    assert open(dump, encoding="utf-8").read() == stored
    _register(module_id, SOUND)
    assert config_mgr.query(f"{module_id}.field")[f"{module_id}.field"] == 8


def test_a_resting_module_stays_resting_when_its_way_back_is_refused(
        setup_demo_environment):
    mgr = setup_demo_environment
    module_id = "resting"
    _register(module_id, SOUND)
    mgr.discard_module(module_id, revive=lambda: None)
    resting = dict(mgr._dormant[module_id])

    _refuse(module_id)

    # still listed, still with its button: the refusal took nothing away
    assert mgr._dormant.get(module_id) == resting
    assert module_id not in mgr._callback_registry
