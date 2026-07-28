# Copyright 2026 saiedt
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A sealed module that serves as the single source of truth with regard to the
declaration, structure and values of config params of arbitrary modules as
specified in GPSMCPMMS_spec.txt.

Apart from few auxiliary classes and functions in the beginning, the module
consists of three friend classes that know each other and benefit from the
expected behavior of each other:
- CvvNode: A node in the cvv tree holding the hierarchical order within the tree.
  There is only one direct instance of it, namely the root node of the tree.
  All the hierarchy is sealed behind the classmethods of CvvNode as the main
  API provider to the config_mgr as conceptualized within GPSMCPMMS_spec.txt.
  The main attributes of tree nodes are:
  + parent: a CvvNode
  + children: a dict mapping child keys to instances of CvvNode.
- CvvPathElem: A subclass of CvvNode that could alternatively have been named
  CvvConfigElem because each path element is actually a config node linked with a
  concrete Declaration and possessing a "current value" (see CvvValue). This
  class concentrates on the essence and nature of a config node as such. The main
  attributes of a path element are:
  + id: str
  + cur_val: CvvValue
  + protected: bool
  + ui_props: A dict with the keys: label, tooltip, placeholder, hidden,
              likely_val, scale_op and scale_factor (derived from s2g_scale),
              acquire_button, test_func and test_func_msg, plus item_template
              (the hidden list item template) on list nodes
- CvvValue: Concerns all issues related to the value of a config node. The main
  attributes of a value are:
  + owner: CvvPathElem
  + kind: simple immutable value versus list versus dict
  + constraints: value constraints as derived from the Declaration of a config
    node
  + source: frontend / backend / none, where the frontend/backend sources may
    additionally be marked as once-only (init_only)
  + value: the current validated value

The main classes are hence CvvPathElem and CvvValue; they are linked with each
other: A CvvValue has a CvvPathElem as owner; vice versa, the same path element
has that value as cur_val. In other words, all path elements possess a value;
from the viewpoint of CvvValue the owner must provide the following callables:
- get_id() and get_path(): return the relative and absolute identifiers of the
  owner, and
- get_child_value() and get_parent_value(): owners are part of a hierarchical
  structure not known to the values per se
Vice versa, path elements make use of the following API of their values:
add_relevance_rule(), check_and_set_value(), check_simple_val(),
get_configurability(), get_value(), is_incomplete(), is_irrelevant(),
is_numeric(), is_valid_child_key(), validate_list_keys() and value_cond_holds().

There is also a structural link between the children of a node and its value: if
a node does not have any children, then the value is a simple, immutable value;
otherwise, the value is either a list or a dict, in which case the keys in the
children dict of the node are either indexes of list items or keys in the dict
value. In any case, a node's cur_val.value is always a valid ready-to-use python
value as opposed to children and parent that are just the traversal means. The
implementation avoids waste of memory by sharing dict and list values across
hierarchies; it then does not need any calculation for deriving the value of
any node, because they are always valid python values, ready to use.
It is an intentional choice to keep the classes in this module as friend classes,
because they just serve an internal organization of code within a module whose
API consists of only classmethods of CvvNode itself, and there is no external
dependency to any subclass of CvvNode. The motto was: In software architecture,
pragmatism should always beat dogma. Principles like the Open-Closed Principle
exist to protect large engineering teams from accidentally breaking shared,
public APIs. But in this case, the entire inheritance tree is a strictly sealed,
private implementation detail hidden behind a few classmethods on CvvNode;
hence, the "costs" of architectural coupling disappear.
Some of the cross-class invariants:
- dict-node children keys == value-dict keys
- for dict values, _push_up_value is the only writer of parent value entries
- list-node value order == ordinal children order, kept aliased with the item
  values by _expand_by_list_value
"""

import ast
import copy
import json
import logging
import operator
import os
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar

CVV_UNKNOWN_PHASE = 0
CVV_MODULE_INIT_PHASE = 1
CVV_MODULE_LOAD_PHASE = 2
CVV_MODULE_SYNC_PHASE = 3
CVV_MODULE_UPDATE_PHASE = 4


class CvvError(Exception):
    """Base exception for all cvv-related errors."""
    _logger = logging.getLogger("CVV_Bootstrap")
    _phase = CVV_UNKNOWN_PHASE

class CvvInitError(CvvError):
    _phase = CVV_MODULE_INIT_PHASE

class CvvLoadError(CvvError):
    _phase = CVV_MODULE_LOAD_PHASE

class CvvSyncError(CvvError):
    _phase = CVV_MODULE_SYNC_PHASE

class CvvUpdateError(CvvError):
    _phase = CVV_MODULE_UPDATE_PHASE


def debug(msg: str) -> None:
    CvvError._logger.log(logging.DEBUG, msg)

def info(msg: str) -> None:
    CvvError._logger.log(logging.INFO, msg)

def warn(msg: str) -> None:
    CvvError._logger.log(logging.WARNING, msg)

def error(msg: str) -> None:
    CvvError._logger.log(logging.ERROR, msg)


# The (module, phase) currently processed by this thread/task; maintained by
# the pipelines in CvvNode so that critical() can classify errors and
# CvvNode.get_type() can resolve type names within the right module namespace.
_current_ctxt: ContextVar = ContextVar("cvv_current_ctxt",
                                       default=(None, CVV_UNKNOWN_PHASE))

@contextmanager
def _phase(module, phase):
    token = _current_ctxt.set((module, phase))
    try:
        yield
    finally:
        _current_ctxt.reset(token)

def get_ctxt_of_current_thread():
    return _current_ctxt.get()

def critical(msg: str) -> None:
    module, phase = get_ctxt_of_current_thread()
    match phase:
        case CvvInitError._phase:
            raise CvvInitError(f"In module '{module}': {msg}")
        case CvvLoadError._phase:
            raise CvvLoadError(f"In module '{module}': {msg}")
        case CvvSyncError._phase:
            raise CvvSyncError(f"In module '{module}': {msg}")
        case CvvUpdateError._phase:
            raise CvvUpdateError(f"In module '{module}': {msg}")
        case _:
            raise CvvError(msg)

def flatten_to_spec(d: dict) -> dict:
    """
    Transforms a deeply nested dictionary by flattening nested dictionary keys
    into dot-separated paths. Lists are kept unchanged in their natural nested
    form as the values of their paths: a list is always imposed as a whole on
    its list node, which flattens each member itself when expanding the list.
    """
    result = {}

    def walk(current_dict: dict, prefix: str = "") -> None:
        for k, v in current_dict.items():
            # Construct the dot-separated path key
            new_key = f"{prefix}.{k}" if prefix else k

            if isinstance(v, dict):
                # Recursively descend into the nested dictionary, carrying the path prefix
                walk(v, new_key)
            else:
                # Lists and leaf values (immutable types) stay unchanged
                result[new_key] = v

    walk(d)
    return result


class CvvValue:
    NO_SOURCE = 0
    SRC_FRONTEND = 1
    SRC_BACKEND = 2
    SRC_FRONTEND_ONCE = 3
    SRC_BACKEND_ONCE = 4

    SIMPLE_KIND = 0
    DICT_KIND = 1
    LIST_KIND = 2

    IMMUTABLE_TYPES = (
        bool, bytes, complex, float, frozenset, int, str, tuple, type(None)
    )
    PRIMITIVE_TYPES = (
        "boolean", "color", "enum", "float", "int",
        "password", "path", "pingable", "string", "url"
    )

    COMPARISON_MAP = {
        "==": operator.eq, "!=": operator.ne,
        "<=": operator.le, ">=": operator.ge,
         "<": operator.lt,  ">": operator.gt
    }

    RANGE_PATTERN = re.compile(
        r"^(-?[0-9]+(?:\.[0-9]+)?)?\.\.(-?[0-9]+(?:\.[0-9]+)?)?$")

    @staticmethod
    def parse_range(range_str, parse_as_int):
        m = (CvvValue.RANGE_PATTERN.match(range_str)
                    if isinstance(range_str, str) and range_str != ".." else
             None)
        if m is None:
            critical(f"Not a range string: {range_str}")

        cast = int if parse_as_int else float
        try:
            return (cast(m.group(1)) if m.group(1) else None,
                    cast(m.group(2)) if m.group(2) else None)
        except Exception:
            critical(f"Range bounds in '{range_str}' do not match the "
                     f"{'int' if parse_as_int else 'float'} type.")

    def accepts_dict_value(self):
        return self._kind == self.DICT_KIND

    def accepts_list_value(self):
        return self._kind == self.LIST_KIND

    def accepts_simple_value(self):
        return self._kind == self.SIMPLE_KIND

    def add_relevance_rule(self, conditional_child, cond):
        if not (self._kind == self.DICT_KIND and isinstance(cond, dict) and
                conditional_child in self._value and
                not conditional_child in self._relevance_rules and
                "child_key" in cond and "op" in cond and "value" in cond):
            critical("We should never get here.")

        if not cond["child_key"] in self._value:
            critical(f"Relevance rule for '{conditional_child}' on unknown "
                     f"sibling '{cond['child_key']}' rejected.")

        self._relevance_rules[conditional_child] = cond

    def check_and_set_value(self, val):
        if self._source == self.NO_SOURCE:
            if self._kind == self.LIST_KIND:
                # spec 2.1 key 4: a high-level fixed_val locks the length of a
                # list, not what its members contain. Accept a list of
                # unchanged length and let every member vet its own value --
                # a member's own fixed_val or init_only still refuses a change
                # (they end up with NO_SOURCE themselves and land in the
                # equality check below).
                return (isinstance(val, list) and
                        len(val) == len(self._value or []) and
                        self._check_and_set_value(val))
            return self._value == val

        if self._kind == self.DICT_KIND:
            warn("dict values may not be set directly.")
            return False

        return self._check_and_set_value(val)

    def check_simple_val(self, val):
        if not (type(val) in self.IMMUTABLE_TYPES and
                self._kind == self.SIMPLE_KIND):
            return False

        if val is None:
            return True

        k, v = next(iter(self._constraints.items()))
        match k:
            case "one_of":
                if isinstance(v, str):
                    # dynamic enum: the options are provided at runtime by a
                    # backend function (see spec 4.9.1); defer the exact check
                    return isinstance(val, str)
                return any(opt["value"] == val for opt in v)
            case "patterned_string":
                return isinstance(val, str) and bool(re.fullmatch(v, val))
            case "ranged_float":
                return (isinstance(val, float) and
                        not isinstance(val, bool) and
                        (v[0] is None or v[0] <= val) and
                        (v[1] is None or val <= v[1])
                    )
            case "ranged_int":
                return (isinstance(val, int) and
                        not isinstance(val, bool) and
                        (v[0] is None or v[0] <= val) and
                        (v[1] is None or val <= v[1])
                    )
            case "type":
                if v == "boolean":
                    return isinstance(val, bool)
                if v == "color":
                    return (
                        isinstance(val, tuple) and len(val) == 3 and
                        all(
                            isinstance(x, int) and
                            not isinstance(x, bool) and
                            -1 < x < 256 for x in val
                        )
                    )
                if v in ("float", "int"):
                    return type(val).__name__ == v
                if not isinstance(val, str):
                    return False
                if v in ("path", "pingable", "url"):
                    return bool(val) and min(val) > ' '
                return True
        return False

    def get_configurability(self):
        return (self._source
                        if self._source < self.SRC_FRONTEND_ONCE else
                self._source - 2)

    def get_value(self):
        return self._value

    def is_incomplete(self):
        if self._kind == self.SIMPLE_KIND:
            return self._value is None

        if self._kind == self.DICT_KIND:
            for child_key in self._value:
                if child_key in self._relevance_rules:
                    if (self._child_cond_holds(
                                self._relevance_rules[child_key]) and
                            self._value[child_key] is None):
                        return True
                elif self._value[child_key] is None:
                    return True
            return False

        return self._constraints["min_size"] > len(self._value)

    def is_irrelevant(self):
        parent_value = self._owner.get_parent_value()
        if parent_value is None or not isinstance(
                                        parent_value._relevance_rules, dict):
            return False

        cond = parent_value._relevance_rules.get(self._owner.get_id())
        return (isinstance(cond, dict) and
                not parent_value._child_cond_holds(cond))

    def is_numeric(self):
        return (self._kind == self.SIMPLE_KIND and (
                "ranged_float" in self._constraints or
                "ranged_int" in self._constraints or
                self._constraints.get("type") in ("float", "int")))

    def is_valid_child_key(self, child_key):
        return (self._kind == self.DICT_KIND and
                child_key in self._value)

    def validate_list_keys(self):
        # deferred part of the list_keys validation:
        # each property must resolve inside the item template
        list_value = self._owner.get_parent_value()
        key_groups = (list_value._constraints.get("keys")
                          if list_value is not None else
                      None)
        if not key_groups:
            return

        if self._kind != self.DICT_KIND:
            critical(f"'list_keys' not allowed for {self._owner.get_path()} "
                      "as its members are scalar values.")

        for group in key_groups:
            for prop in group:
                if prop not in self._value:
                    critical(f"Cannot resolve attribute '{prop}' "
                              "inside keys constraint context.")

    def value_cond_holds(self, op, r_val):
        if isinstance(self._value, dict) or isinstance(self._value, list):
            warn(f"{self._value} cannot be compared with {r_val}.")
            return False

        l_val = self._value

        if op == "~=":
            return isinstance(l_val, str) and isinstance(r_val, str
                                        ) and bool(re.search(r_val, l_val))
        if l_val is None:
            if op == "==":
                return r_val is None
            if op == "!=":
                return r_val is not None
            return False

        if op not in self.COMPARISON_MAP:
            return False
        try:
            return self.COMPARISON_MAP[op](l_val, r_val)
        except TypeError:
            return op == "!="

    def _add_list_constraints(self, list_decl):
        if "list_size" in list_decl:
            fr, to = CvvValue.parse_range(list_decl["list_size"], True)
            if fr is None:
                fr = 0
            if to is None:
                to = 100
            # both bounds are inclusive member counts; the two-digit ordinal
            # ids "00".."99" limit every list to at most 100 members
            if fr < 0 or fr > to or to > 100:
                critical(f"Invalid size range: {list_decl['list_size']}")
            self._constraints["min_size"] = fr
            self._constraints["max_size"] = to
        else:
            self._constraints["min_size"] = 0
            self._constraints["max_size"] = 100
        if "list_keys" in list_decl:
            # only structural validation here; the check that each property
            # resolves inside the item template is done by the owner after
            # the template has been created (see validate_list_keys()).
            keys = list_decl["list_keys"]
            if not isinstance(keys, list) or not keys:
                critical(f"`list_keys` is not a non-empty list: {type(keys)}")

            validated_keys = []
            for i, constraint in enumerate(keys):
                if not isinstance(constraint, list) or not constraint:
                    critical(f"Constraint at index {i} must be "
                             f"a non-empty list. Got: {constraint}")

                t = tuple(constraint)
                if len(set(t)) < len(constraint):
                    critical("Redundant properties within a single group: "
                             f"{constraint}")

                if t in validated_keys:
                    critical("Redundancy error: "
                            f"{constraint} defined multiple times.")
                else:
                    validated_keys.append(t)

            self._constraints["keys"] = tuple(validated_keys)

    def _add_simple_val_constraints(self, decl):
        type_str = decl.get("resolved_type", decl.get("type"))
        if not type_str in self.PRIMITIVE_TYPES:
            critical(f"Specified simple type is unknown: '{type_str}'.")

        bound_to = decl.get("bound_to", "")
        if bound_to and isinstance(bound_to, str):
            match type_str:
                case "float":
                    self._constraints["ranged_float"] = (
                            CvvValue.parse_range(bound_to, False))
                case "int":
                    self._constraints["ranged_int"] = (
                            CvvValue.parse_range(bound_to, True))
                case "string":
                    self._constraints["patterned_string"] = bound_to
                case _:
                    critical(f"Bounded '{type_str}' rejected.")
        else:
            match type_str:
                case "enum":
                    vals = decl.get("values", {})
                    if isinstance(vals, str) and vals.strip():
                        # dynamic enum: options resolved at runtime by the
                        # named backend function (see spec 4.9.1)
                        self._constraints["one_of"] = vals.strip()
                        return
                    if not isinstance(vals, dict):
                        critical("enum 'values' must be a dict or the name "
                                 "of a backend function.")
                    options = []
                    for k, v in vals.items():
                        opt = {"value": k, "label": k}
                        if isinstance(v, dict):
                            if "label" in v:
                                opt["label"] = v["label"]
                            else:
                                warn(f"Missing option label for enum value {k}.")
                            if "tooltip" in v:
                                opt["tooltip"] = v["tooltip"]
                        options.append(opt)
                    if len(options) == 0:
                        critical(f"enum has no options.")
                    self._constraints["one_of"] = options
                case (
                    "boolean" | "color" | "float" | "int" | "password" |
                    "path" | "pingable" | "string" | "url"
                ):
                    self._constraints["type"] = type_str
                case _:
                    critical(f"Unknown simple type specification {type_str}.")

    def _child_cond_holds(self, cond):
        if not isinstance(cond, dict) or not all(
                    p in cond for p in ("child_key", "op", "value")):
            error(f"Not a condition: {cond}.")
            return False

        cv = self._owner.get_child_value(cond["child_key"])
        if not isinstance(cv, CvvValue):
            warn(f"Left operand not found: {cond}.")
            return False

        return cv.value_cond_holds(cond["op"], cond["value"])

    def _check_and_set_value(self, val):
        # sets only simple and list values
        result = True
        if not self.check_simple_val(val):
            if self._kind != self.LIST_KIND:
                return False
            if val is None:
                val = []
            elif isinstance(val, list):
                # "min_size" check not needed because partial values are valid
                # even if partial values will mark the list as incomplete
                list_val = val[:self._constraints["max_size"]]
                if len(val) > len(list_val):
                    warn(f"The provided complex value '{val}' did not conform "
                         f"with the constraints on '{self._owner.get_path()}'.")
                    result = False
                    val = list_val
            else:
                return False

        self._value = val
        if val and self._source > self.SRC_BACKEND:
            self._source = self.NO_SOURCE
        self._push_up_value()
        self._journal_value()
        return result

    def _journal_value(self):
        # write-ahead persistence of verified user input; a successful SYNC
        # (full dump of the module value) resets the journal
        module, phase = get_ctxt_of_current_thread()
        if phase != CVV_MODULE_UPDATE_PHASE or not module:
            return

        if self._kind == self.LIST_KIND:
            CvvNode._append_journal_entry(module, self._owner.get_path(),
                                          self._value)
            return

        # values inside lists are not journaled themselves: ordinal ids are
        # positions, not identities, so such entries could not be replayed
        # reliably; they are covered by their list's whole-value entry
        parent_value = self._owner.get_parent_value()
        while parent_value is not None:
            if parent_value._kind == self.LIST_KIND:
                return
            parent_value = parent_value._owner.get_parent_value()

        CvvNode._append_journal_entry(module, self._owner.get_path(),
                                      self._value)

    def _push_up_value(self):
        # push up the value only if parent has a dict value; list parents get
        # their elements aliased with the item values by _expand_by_list_value
        # note that dict content change does not affect ancestors
        parent_value = self._owner.get_parent_value()
        if parent_value is not None and parent_value._kind == self.DICT_KIND:
            my_id = self._owner.get_id()
            if not my_id in parent_value._value:
                critical("My id is not a valid key in the parent dict.")
            my_value_in_parent_dict = parent_value._value[my_id]
            if (parent_value._source == self.NO_SOURCE and
                my_value_in_parent_dict is not None and
                self._value != my_value_in_parent_dict
            ):
                critical("Fixed value of parent may not be overwritten.")

            # bottom-up push of value:
            parent_value._value[my_id] = self._value

    def _get_val_to_inherit(self, child_key):
        if not isinstance(child_key, str) or not child_key:
            critical(f"Invalid child_key=={child_key} rejected.")

        if self._kind == self.LIST_KIND:
            if child_key.isdigit():
                idx = int(child_key)
                if 0 <= idx < len(self._value):
                    return self._value[idx], True
            else:
                # the item template inherits nothing from the list value
                return None, False
        elif isinstance(self._declared_val, dict):
            return (
                (self._declared_val[child_key], self._source == self.NO_SOURCE)
                        if child_key in self._declared_val else
                (None, False)
            )

        critical(f"'{child_key}' is not a child of {self._owner.get_path()}.")

    def _init_value(self, decl):
        dv = decl.get("default_val")
        fv = decl.get("fixed_val")
        if dv is not None and fv is not None:
            critical("Simultaneous declaration of a fixed and a default value "
                     f"on {self._owner.get_path()}.")
        if decl.get("init_only", False) and (dv is not None or fv is not None):
            critical("init_only may not be combined with a fixed or a default "
                     f"value on {self._owner.get_path()}.")

        self._declared_val = None
        self._source = (
            (bool(decl.get("init_only", False)) << 1) +
            bool(decl.get("backend_provided", False)) + 1
        )
        parent_value = self._owner.get_parent_value()
        iv, imposed = ( (None, False)
                            if parent_value is None else
                        parent_value._get_val_to_inherit(self._owner.get_id())
                    )
        if iv is not None:
            if imposed:
                if fv and fv != iv:
                    critical(f"Conflicting spec of fixed values for "
                             f"{self._owner.get_path()}.")
                self._declared_val = iv
                if fv or self._source > self.SRC_BACKEND:
                    self._source = self.NO_SOURCE
            elif fv:
                self._declared_val = fv
                self._source = self.NO_SOURCE
            else:
                # a value provided by the parent's value is more specific
                # than this declaration's own default_val
                self._declared_val = iv
        elif fv:
            self._declared_val = fv
            self._source = self.NO_SOURCE
        else:
            self._declared_val = dv

        if self._kind == self.DICT_KIND:
            if self._declared_val is None:
                self._declared_val = {}
            elif isinstance(self._declared_val, dict):
                for k in self._declared_val:
                    if not k in self._value:
                        critical(f"Unknown child key '{k}' in declared value of "
                                 f"{self._owner.get_path()}")
            else:
                critical("Conflicting type and value declarations: "
                        f"{self._owner.get_path()}")
            self._push_up_value()
        elif not self._check_and_set_value(self._declared_val):
            critical("Conflicting type and value declarations: "
                    f"{self._owner.get_path()}")

    def __init__(self, owner: 'CvvPathElem', decl: dict):
        if not (isinstance(owner, CvvPathElem) and isinstance(decl, dict)):
            critical("Type-check of parameters failed.")

        type_spec = decl.get("resolved_type", decl.get("type"))
        is_list = decl.get("is_list")
        if not (type_spec and (
                    (isinstance(type_spec, dict) and isinstance(is_list, bool))
                 or isinstance(type_spec, str))
        ):
            critical("Needed type spec not found.")

        self._constraints = {}
        self._declared_val = None
        self._kind = self.SIMPLE_KIND
        self._owner = owner
        self._relevance_rules = None
        self._source = None
        self._value = None

        if isinstance(type_spec, str):
            self._add_simple_val_constraints(decl)
        elif is_list:
            self._kind = self.LIST_KIND
            self._add_list_constraints(type_spec)
            self._value = []
        else:
            self._kind = self.DICT_KIND
            self._relevance_rules = {}
            # just fix the structure of the value
            self._value = {}
            for k in type_spec:
                self._value[k] = None

        self._init_value(decl)


class CvvNode:
    _database_dir = None
    _dump_file_name = "mod_tree.dump"
    _global_lock = threading.RLock()
    _holder = None
    _journal_file_name = "leaf_update.log"
    _module_locks = {}
    _root_instance = None
    _type_context = {}

    #
    # internal helpers
    #
    @classmethod
    def _append_journal_entry(cls, module, path, value):
        try:
            m_dir = cls._module_dir(module)
            os.makedirs(m_dir, exist_ok=True)
            with open(os.path.join(m_dir, cls._journal_file_name),
                      "a", encoding="utf-8") as f:
                f.write(f"{time.time()}!{path}={value!r}\n")
        except OSError as exc:
            # the value is applied in memory and the following SYNC persists
            # it anyway, so a journaling problem must not abort the update
            error(f"Journaling '{path}' failed: {exc}")

    @classmethod
    def _backup_module_data(cls, module, val_data):
        """
        Persists the module's current value as the new checkpoint:
        - writes {"saved_at": <now>, "value": val_data} via repr() to a temp
          file and moves it atomically to ${_database_dir}/module/${dump},
          keeping the previous checkpoint as *.old
        - resets the journal, whose entries are all covered by the new dump
        """
        m_dir = cls._module_dir(module)
        dump_path = os.path.join(m_dir, cls._dump_file_name)
        tmp_path = dump_path + ".tmp"
        journal_path = os.path.join(m_dir, cls._journal_file_name)
        try:
            os.makedirs(m_dir, exist_ok=True)
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(repr({"saved_at": time.time(), "value": val_data}))
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(dump_path):
                os.replace(dump_path, dump_path + ".old")
            os.replace(tmp_path, dump_path)
            if os.path.exists(journal_path):
                os.remove(journal_path)
        except OSError as exc:
            critical(f"Backup of module '{module}' failed: {exc}")

    @classmethod
    def _check_holder(cls, holder):
        if holder is None or holder != cls._holder:
            critical("Unauthorized access rejected.")

    @classmethod
    def _get_module_lock(cls, module, create):
        with cls._global_lock:
            lock = cls._module_locks.get(module)
            if create:
                if lock is not None:
                    critical(f"Module '{module}' is already registered.")
                lock = threading.RLock()
                cls._module_locks[module] = lock
            elif lock is None:
                critical(f"No such module: {module}.")
        return lock

    @classmethod
    def _load_and_merge_module_data(cls, module, m_node):
        """
        Read-only merge of the persisted module state into the freshly
        initialized subtree: first the last checkpoint (dump), then all
        journal entries that are newer than the checkpoint. The files are
        rotated by the SYNC phase that follows immediately.
        """
        m_dir = cls._module_dir(module)
        dump_path = os.path.join(m_dir, cls._dump_file_name)

        saved_at = 0.0
        payload = cls._read_dump(dump_path)
        if payload is None:
            payload = cls._read_dump(dump_path + ".old")
            if payload is not None:
                warn(f"Module '{module}': recovered from the backup dump.")
        if isinstance(payload, dict):
            saved_at = payload.get("saved_at", 0.0)
            value = payload.get("value")
            if isinstance(value, dict):
                rejected = []
                m_node.impose_value(value, rejected)
                if rejected:
                    warn(f"Module '{module}': persisted values for "
                         f"{rejected} no longer conform with the "
                         "declarations and were skipped.")

        try:
            with open(os.path.join(m_dir, cls._journal_file_name),
                      encoding="utf-8") as f:
                journal_lines = f.readlines()
        except FileNotFoundError:
            return
        except OSError as exc:
            warn(f"Module '{module}': unreadable journal ignored ({exc}).")
            return

        for line in journal_lines:
            entry = cls._parse_journal_entry(line)
            if entry is None:
                continue
            ts, path, value = entry
            if ts <= saved_at:
                continue
            sp = path.split(".", 1)
            if sp[0] != module or len(sp) != 2 or not sp[1]:
                warn(f"Skipping foreign journal entry for '{path}'.")
                continue
            matched = []
            try:
                m_node.get_nodes_by_path(sp[1], matched)
            except CvvError:
                matched = []
            if len(matched) == 1:
                if not matched[0].impose_value(value):
                    warn(f"Journal entry for '{path}' applied partially.")
            else:
                warn(f"Skipping journal entry for unknown node '{path}'.")

    @classmethod
    def _get_single_node(cls, holder, path):
        cls._check_holder(holder)
        if not isinstance(path, str) or not path.strip():
            return None
        sp = path.strip().split(".", 1)
        module = sp[0].strip()
        sub_path = sp[1].strip() if len(sp) == 2 else ""
        with cls._global_lock:
            lock = cls._module_locks.get(module)
            m_node = cls._root_instance.get_child(module)
        if lock is None or not isinstance(m_node, CvvPathElem):
            return None
        with lock:
            if not sub_path:
                return m_node
            matched = []
            try:
                m_node.get_nodes_by_path(sub_path, matched)
            except CvvError:
                return None
            return matched[0] if len(matched) == 1 else None

    @classmethod
    def _locked_modules(cls):
        with cls._global_lock:
            return [(m_id, m_node, cls._module_locks.get(m_id))
                    for m_id, m_node in cls._root_instance._children.items()
                    if isinstance(m_node, CvvPathElem)]

    @classmethod
    def _module_dir(cls, module):
        return os.path.join(cls._database_dir, module)

    @classmethod
    def _parse_journal_entry(cls, line):
        line = line.strip()
        if not line:
            return None
        try:
            head, raw_val = line.split("=", 1)
            ts_str, path = head.split("!", 1)
            return float(ts_str), path, ast.literal_eval(raw_val)
        except (SyntaxError, ValueError):
            warn(f"Skipping malformed journal entry: {line[:80]}")
            return None

    @classmethod
    def _read_dump(cls, path):
        try:
            with open(path, encoding="utf-8") as f:
                return ast.literal_eval(f.read())
        except FileNotFoundError:
            return None
        except (OSError, SyntaxError, ValueError) as exc:
            warn(f"Ignoring unreadable dump '{path}': {exc}")
            return None

    #
    # API usable by holder objects
    #
    @classmethod
    def config_ready(cls, holder, path):
        cls._check_holder(holder)
        if path is None:
            path = ""
        elif not isinstance(path, str):
            return False
        else:
            path = path.strip()
        if path == "*":
            path = ""

        sub_path = ""
        if path:
            sp = path.split(".", 1)
            module = sp[0].strip()
            sub_path = sp[1].strip() if len(sp) == 2 else ""
            module_scope = [scoped for scoped in cls._locked_modules()
                            if module in ("*", scoped[0])]
        else:
            module_scope = cls._locked_modules()

        for m_id, m_node, lock in module_scope:
            if lock is None:
                continue
            with lock:
                if sub_path:
                    matched = []
                    m_node.get_nodes_by_path(sub_path, matched)
                else:
                    matched = [m_node]
                if any(not n.subtree_ready() for n in matched):
                    return False
        return True

    @classmethod
    def get_cvv_json_dump(cls, holder):
        cls._check_holder(holder)
        dump = {}
        for m_id, m_node, lock in cls._locked_modules():
            if lock is None:
                continue
            with lock:
                dump[m_id] = m_node.dump_node()
        return json.dumps(dump, ensure_ascii=False)

    @classmethod
    def get_node_constraints(cls, holder, path):
        """
        Returns a deep copy of the value constraints of the single node
        addressed by `path`, or None if the path does not resolve; note that
        the constraints of every node are fixed at INIT time.
        """
        node = cls._get_single_node(holder, path)
        return (copy.deepcopy(node._cur_val._constraints)
                    if node is not None else
                None)

    @classmethod
    def get_test_func(cls, holder, path):
        """
        Returns the test_func callable declared for the single node addressed
        by `path` (spec 4.9.4), or None.
        """
        node = cls._get_single_node(holder, path)
        return node._ui_props.get("test_func") if node is not None else None

    @classmethod
    def get_protected_paths(cls, holder, module):
        cls._check_holder(holder)
        lock = cls._get_module_lock(module, create=False)
        with lock:
            with cls._global_lock:
                m_node = cls._root_instance.get_child(module)
            collected = []
            if isinstance(m_node, CvvPathElem):
                m_node.collect_protected_nodes(collected)
            return [n.get_path() for n in collected]

    @classmethod
    def init_module(cls, holder, module: str, decl: dict, type_context: dict):
        cls._check_holder(holder)
        if not isinstance(module, str) or not module.strip():
            critical("Module id must be a non-empty string.")

        lock = cls._get_module_lock(module, create=True)
        with lock:
            with cls._global_lock:
                cls._type_context[module] = type_context

            # PIPELINE EXECUTION CHAIN: init -> load&merge -> sync
            with _phase(module, CVV_MODULE_INIT_PHASE):
                m_node = CvvPathElem(cls._root_instance, module, decl)
            with _phase(module, CVV_MODULE_LOAD_PHASE):
                cls._load_and_merge_module_data(module, m_node)
            with _phase(module, CVV_MODULE_SYNC_PHASE):
                cls._backup_module_data(module, m_node.get_value())

            return copy.deepcopy(m_node.get_value())

    @classmethod
    def normalize_json_value(cls, holder, module, config_value):
        """
        Normalizes a JSON-borne update payload to the internal value forms
        expected by the declarations (spec 4.7 a): color lists become tuples
        and numbers are coerced to the declared int/float type. Returns a
        normalized deep copy; the original payload stays untouched.
        """
        cls._check_holder(holder)
        if not isinstance(config_value, dict):
            return config_value

        lock = cls._get_module_lock(module, create=False)
        with lock:
            with cls._global_lock:
                m_node = cls._root_instance.get_child(module)
            if not isinstance(m_node, CvvPathElem):
                critical(f"No such module: {module}.")
            return m_node._normalize_json(copy.deepcopy(config_value))

    @classmethod
    def protected_params_ready(cls, holder):
        cls._check_holder(holder)
        for m_id, m_node, lock in cls._locked_modules():
            if lock is None:
                continue
            with lock:
                collected = []
                m_node.collect_protected_nodes(collected)
                if any(not n.subtree_ready() for n in collected):
                    return False
        return True

    @classmethod
    def query(cls, holder, path):
        cls._check_holder(holder)
        if not isinstance(path, str) or not path.strip():
            critical("query() needs a non-empty, module-rooted path.")

        result = {}
        sp = path.strip().split(".", 1)
        module = sp[0].strip()
        sub_path = sp[1].strip() if len(sp) == 2 else ""
        with cls._global_lock:
            lock = cls._module_locks.get(module)
            m_node = cls._root_instance.get_child(module)
        if lock is None or not isinstance(m_node, CvvPathElem):
            return result

        with lock:
            if sub_path:
                matched = []
                m_node.get_nodes_by_path(sub_path, matched)
            else:
                matched = [m_node]
            for n in matched:
                result[n.get_path()] = copy.deepcopy(n.get_value())
        return result

    @classmethod
    def register(cls, holder, data_dir):
        with cls._global_lock:
            if (
                cls._holder is not None or
                cls._root_instance is not None or
                holder is None
            ):
                critical("Provided `holder` is invalid or already set.")

            if not os.path.isdir(data_dir):
                critical(f"No such folder: {data_dir}")

            cls._holder = holder
            cls._database_dir = data_dir
            return cls()

    @classmethod
    def set_logger(cls, holder, logger):
        cls._check_holder(holder)
        if isinstance(logger, logging.Logger):
            CvvError._logger = logger

    @classmethod
    def update_module(cls, holder, module: str, config_value: dict):
        cls._check_holder(holder)
        if not isinstance(module, str) or not module.strip():
            critical("Module id must be a non-empty string.")

        if not isinstance(config_value, dict):
            critical("config_value must be a dict object.")

        lock = cls._get_module_lock(module, create=False)
        with lock:
            with cls._global_lock:
                m_node = cls._root_instance.get_child(module)
            if not isinstance(m_node, CvvPathElem):
                critical(f"No such module: {module}.")

            # PIPELINE EXECUTION CHAIN: update -> sync
            rejected = []
            with _phase(module, CVV_MODULE_UPDATE_PHASE):
                m_node.impose_value(config_value, rejected)
            with _phase(module, CVV_MODULE_SYNC_PHASE):
                cls._backup_module_data(module, m_node.get_value())

            return rejected, copy.deepcopy(m_node.get_value())

    def __init__(self):
        if self._root_instance is None:
            self._parent = None
            self._children = {}
            CvvNode._root_instance = self
        else:
            critical("No further instances allowed.")

    def add_child(self, key, child: 'CvvNode') -> bool:
        if not (isinstance(self._children, dict)
                and isinstance(child, CvvNode)
                and key and not key in self._children):
            return False
        if self.is_root():
            # module nodes are inserted concurrently by parallel init_module
            # pipelines; all other nodes live inside one module subtree, which
            # is guarded by its module lock
            with CvvNode._global_lock:
                self._children[key] = child
        else:
            self._children[key] = child
        child._parent = self
        return True

    def get_child(self, child_id) -> 'CvvNode':
        return (self._children.get(child_id)
                    if isinstance(self._children, dict) and child_id else
                None)

    def get_type(self, type_name):
        module, phase = get_ctxt_of_current_thread()
        module_types = None if module is None else self._type_context.get(module)
        return (module_types.get(type_name)
                    if isinstance(module_types, dict) else
                None)

    def is_list_root(self):
        return False

    def is_root(self):
        return self._parent is None


class CvvPathElem(CvvNode):
    CONDITION_OPERATIONS = ("==", "!=", "<=", ">=", "<", ">", "~=")

    DECLARATION_KEYS = frozenset((
        # the fixed set of keys specified in section 2.1 of the spec
        "backend_provided", "default_val", "fixed_val", "hidden", "init_only",
        "label", "likely_val", "placeholder", "protected", "relevance",
        "s2g_scale", "tooltip", "type",
        # type-specific sub-properties (see section 2.1, key 3)
        "acquire_button", "bound_to", "values",
        # test support (see section 4.9.4 of the spec)
        "test_func", "test_func_msg",
        # annotations added internally during type resolution
        "is_list", "resolved_type",
    ))
    LIST_TYPE_KEYS = frozenset(("list_keys", "list_member", "list_size"))

    LIST_ITEM_TEMPLATE_ID = "_list_item_template"

    @staticmethod
    def is_valid_id(n_id):
        return (isinstance(n_id, str) and
                not n_id.startswith("list_") and
                bool(re.match(r"^[-0-9A-Za-z_]+$", n_id))
            )

    def collect_protected_nodes(self, collector):
        if self._protected:
            collector.append(self)
        elif isinstance(self._children, dict):
            for c in self._children.values():
                c.collect_protected_nodes(collector)

    def dump_node(self) -> dict:
        d = {
            "path": self.get_path(),
            "ui": dict(self._ui_props),
            "constraints": self._cur_val._constraints,
            "configurability": self._cur_val.get_configurability(),
        }
        if self._protected:
            d["protected"] = True
        if self._cur_val._relevance_rules:
            # the editor needs the conditions to show/hide children live
            d["relevance"] = self._cur_val._relevance_rules
        if "test_func" in d["ui"]:
            # the callable itself is backend-internal; the frontend only
            # needs to know that a test action exists for this node
            d["ui"]["test_func"] = True
        if self._children is None:
            d["value"] = self._cur_val.get_value()
        elif self.is_list_root():
            d["value"] = self._cur_val.get_value()
            d["item_template"] = d["ui"].pop("item_template").dump_node()
        else:
            d["children"] = {k: c.dump_node()
                             for k, c in self._children.items()}
        return d

    def get_child_value(self, child_id):
        c = self.get_child(child_id)
        return c._cur_val if isinstance(c, CvvPathElem) else None

    def get_id(self) -> str:
        return self._id

    def get_nodes_by_path(self, path, collector):
        if not path:
            critical("Empty path rejected.")

        if self.is_leaf():
            critical("Reached a leaf node with non-empty path.")

        sp_p = path.split(".", 1)
        path_elem = sp_p[0].strip()
        if not path_elem:
            critical(f"Malformed path: {path}")
        next_path = sp_p[1].strip() if len(sp_p) == 2 else ""

        c = self.get_child(path_elem)
        if c is None and path_elem == CvvPathElem.LIST_ITEM_TEMPLATE_ID:
            # declarations of future list members (e.g. their dynamic enums
            # or test funcs) are addressed via the hidden item template
            template = self._ui_props.get("item_template")
            if isinstance(template, CvvPathElem):
                c = template
        if c is not None:
            if next_path:
                c.get_nodes_by_path(next_path, collector)
            else:
                collector.append(c)

        elif path_elem == "*":
            for c in self._children.values():
                if next_path:
                    # children without a matching sub-path simply do not match
                    if not c.is_leaf():
                        c.get_nodes_by_path(next_path, collector)
                else:
                    collector.append(c)
        else:
            cond = self._parse_cond_on_child(path_elem)
            c = self.get_child(cond["child_key"])
            if c is not None and c._cur_val.value_cond_holds(
                                                cond["op"], cond["value"]):
                # the predicate held, so this node stays selected;
                # the remaining path continues from here
                if next_path:
                    self.get_nodes_by_path(next_path, collector)
                else:
                    collector.append(self)

    def get_parent_value(self):
        return (self._parent._cur_val
                    if isinstance(self._parent, CvvPathElem) else
                None)

    def get_path(self) -> str:
        path_parts = []
        curr = self
        while isinstance(curr, CvvPathElem):
            path_parts.append(str(curr._id))
            curr = curr._parent
        return ".".join(reversed(path_parts))

    def get_value(self):
        return self._cur_val.get_value()

    def impose_value(self, val, rejected=None) -> bool:
        """
        Applies all applicable values and skips only values not applicable,
        collecting the paths of the skipped ones in `rejected` (if provided).
        """
        if self.is_leaf():
            if (val is None and get_ctxt_of_current_thread()[1] ==
                                                    CVV_MODULE_LOAD_PHASE):
                # merging persisted state: a persisted "no value" must not
                # override a declared default or fixed value
                return True
            if self._cur_val.check_and_set_value(val):
                return True
            self._note_rejection(rejected)
            return False

        if self.is_list_root():
            list_level_check = self._cur_val.check_and_set_value(val)
            if not list_level_check:
                self._note_rejection(rejected)
            return self._expand_by_list_value(rejected) and list_level_check

        if not isinstance(val, dict):
            self._note_rejection(rejected)
            return False

        val = flatten_to_spec(val)
        result = True
        for k, v in val.items():
            nodes = []
            try:
                self.get_nodes_by_path(k, nodes)
            except CvvError:
                nodes = []
            if len(nodes) == 1:
                if not nodes[0].impose_value(v, rejected):
                    result = False
            else:
                warn(f"Unknown node: {self.get_path()}.{k}")
                if rejected is not None:
                    rejected.append(f"{self.get_path()}.{k}")
                result = False
        return result

    def is_leaf(self):
        return isinstance(self._parent, CvvPathElem) and self._children is None

    def is_list_item(self):
        return (isinstance(self._parent, CvvPathElem) and
                self._parent.is_list_root() and self._id.isdigit())

    def is_list_root(self):
        return (isinstance(self._parent, CvvPathElem) and
                isinstance(self._children, dict) and
                isinstance(self._item_decl, dict))

    def is_module_node(self):
        return (self._parent.is_root() and not self._id.isdigit() and
                isinstance(self._children, dict))

    def is_prop_node(self):
        return isinstance(self._parent, CvvPathElem) and not self._id.isdigit()

    def parse_cond_on_sibling(self, cond_str: str):
        if not self.is_prop_node():
            critical("I do not have any siblings.")
        return self._parent._parse_cond_on_child(cond_str)

    def subtree_ready(self) -> bool:
        if self._cur_val.is_irrelevant():
            return True

        if self._cur_val.is_incomplete():
            return False

        if isinstance(self._children, dict):
            return all(c.subtree_ready() for c in self._children.values())
        else:
            return True

    def _expand_by_list_value(self, rejected=None):
        list_val = self._cur_val.get_value()
        elems = list(list_val) if isinstance(list_val, list) else []
        cl = len(self._children)
        vl = len(elems)
        num_updatables = cl if cl < vl else vl
        while cl < vl:
            # new items get their imposed values already at construction
            CvvPathElem(self, f"{cl:02}", self._item_decl)
            cl += 1
        while cl > vl:
            k, oi = self._children.popitem()
            oi._parent = None
            cl -= 1
        result = True
        for i in range(0, vl):
            item = self._children.get(f"{i:02}")
            if item is None:
                critical("Inconsistent list internal state.")
            if (i < num_updatables and
                    not item.impose_value(elems[i], rejected)):
                result = False
            # alias the list element with the item's composed value, so that
            # defaults and salvaged parts materialize in the list value, too
            self._cur_val._value[i] = item.get_value()
        return result

    def _expand_by_type_decl(self, type_decl):
        for prop, p_decl in type_decl.items():
            if (
                not isinstance(p_decl, dict) or
                not isinstance(prop, str) or
                prop.isdigit()
            ):
                critical("Not a named type declaration.")
            CvvPathElem(self, prop, p_decl)
            if "relevance" in p_decl:
                cond = self._parse_cond_on_child(p_decl["relevance"])
                self._cur_val.add_relevance_rule(prop, cond)

    def _normalize_json(self, val):
        cv = self._cur_val
        if cv._kind == CvvValue.SIMPLE_KIND:
            if isinstance(val, bool):
                return val
            if (cv._constraints.get("type") == "color" and
                    isinstance(val, list) and len(val) == 3):
                return tuple(val)
            if (isinstance(val, int) and
                    ("ranged_float" in cv._constraints or
                     cv._constraints.get("type") == "float")):
                return float(val)
            if (isinstance(val, float) and val.is_integer() and
                    ("ranged_int" in cv._constraints or
                     cv._constraints.get("type") == "int")):
                return int(val)
            return val

        if cv._kind == CvvValue.LIST_KIND:
            template = self._ui_props.get("item_template")
            if not (isinstance(val, list) and
                    isinstance(template, CvvPathElem)):
                return val
            return [template._normalize_json(item) for item in val]

        # dict node: normalize all values addressing known (possibly
        # dotted-path) children; unknown keys stay for later rejection
        if not isinstance(val, dict):
            return val
        normalized = {}
        for k, v in val.items():
            c = self.get_child(k) if isinstance(k, str) else None
            if c is None and isinstance(k, str) and "." in k:
                nodes = []
                try:
                    self.get_nodes_by_path(k, nodes)
                except CvvError:
                    nodes = []
                if len(nodes) == 1:
                    c = nodes[0]
            normalized[k] = (c._normalize_json(v)
                                 if isinstance(c, CvvPathElem) else
                             v)
        return normalized

    def _note_rejection(self, rejected):
        if rejected is not None:
            rejected.append(self.get_path())

    def _parse_cond_on_child(self, cond_str: str):
        if self.is_leaf() or self.is_list_root():
            critical("Violation of rule-spec for conds on path elems.")

        if not isinstance(cond_str, str):
            critical("Violation of rule-spec for conds on path elems.")

        child, op, value = "", "", ""
        for ro in CvvPathElem.CONDITION_OPERATIONS:
            if ro in cond_str:
                parts = cond_str.strip().split(ro, 1)
                child = parts[0].strip()
                if not child or not self._cur_val.is_valid_child_key(child):
                    critical(f"Unknown child '{child}' of {self.get_path()}.")
                op = ro
                value = parts[1].strip()
                break
        if not op:
            critical("Violation of rule-spec for conds on path elems.")
        try:
            return {
                    "child_key": child,
                    "op": op,
                    "value": json.loads(value if value else "null")
                }
        except Exception:
            critical("Violation of rule-spec for conds on path elems.")

    def __init__(self, parent: CvvNode, id: str, decl):
        if not (isinstance(parent, CvvNode) and CvvPathElem.is_valid_id(id)):
            critical(f"Invalid `parent`=={parent} and/or `id`=={id}.")

        if not (isinstance(decl, dict) and
                isinstance(decl.get("type"), str) and decl["type"].strip()):
            critical(f"Invalid Declaration: {decl}.")

        unknown_keys = set(decl) - self.DECLARATION_KEYS
        if unknown_keys:
            critical(f"Unknown Declaration key(s) {sorted(unknown_keys)} "
                     f"in the declaration of '{id}'.")

        self._id = id
        if id == self.LIST_ITEM_TEMPLATE_ID:
            if not parent.is_list_root() or "item_template" in parent._ui_props:
                critical(f"Invalid id rejected: {id}.")
            self._parent = parent
        else:
            parent.add_child(id, self)

        type_spec = decl["type"].strip()
        type_decl = CvvNode._root_instance.get_type(type_spec)
        if isinstance(type_decl, dict):
            # the original "type" stays untouched: the resolution is recorded
            # in "resolved_type" (idempotent for shared type templates)
            decl["resolved_type"] = type_decl
            self._children = {}
            if type_spec.endswith("_list") and "list_member" in type_decl:
                unknown_keys = set(type_decl) - self.LIST_TYPE_KEYS
                if unknown_keys:
                    critical(f"Unknown key(s) {sorted(unknown_keys)} in the "
                             f"named list type '{type_spec}'.")
                self._item_decl = type_decl["list_member"]
                decl["is_list"] = True
            else:
                decl["is_list"] = False
                self._item_decl = None
        else:
            self._children = None
            self._item_decl = None

        self._cur_val = CvvValue(self, decl)
        self._protected = decl.get("protected", False)

        self._ui_props = {}
        for k in ("label", "tooltip", "placeholder"):
            v = decl.get(k)
            if isinstance(v, str) and v.strip():
                self._ui_props[k] = v.strip()
            elif v is not None:
                critical(f"As value for {k}, {v} had to be a string object.")
        self._ui_props["hidden"] = decl.get("hidden", False)
        lv = decl.get("likely_val")
        if lv is not None:
            if self._cur_val.check_simple_val(lv):
                self._ui_props["likely_val"] = lv
            else:
                critical(f"Invalid likely_val: '{lv}'")
        if "s2g_scale" in decl:
            scale_str = str(decl["s2g_scale"])
            if not self._cur_val.is_numeric():
                critical("s2g_scale is only applicable to int/float values "
                         f"({self.get_path()}).")
            try:
                op, f = re.match(r"^([*/])([0-9.]+)$", scale_str.strip()
                                ).groups()
                self._ui_props["scale_op"] = op
                self._ui_props["scale_factor"] = f
            except Exception:
                critical(f"Invalid scale format: '{scale_str}'")
        acquire_button = decl.get("acquire_button")
        if decl.get("backend_provided", False):
            if not (isinstance(acquire_button, str) and
                    acquire_button.strip()):
                critical("backend_provided values need an 'acquire_button' "
                         f"label ({self.get_path()}).")
            self._ui_props["acquire_button"] = acquire_button.strip()
        elif acquire_button is not None:
            critical("'acquire_button' is only applicable together with "
                     f"backend_provided ({self.get_path()}).")
        test_func = decl.get("test_func")
        if test_func is not None:
            if not callable(test_func):
                critical(f"'test_func' must be callable ({self.get_path()}).")
            self._ui_props["test_func"] = test_func
        test_func_msg = decl.get("test_func_msg")
        if test_func_msg is not None:
            if test_func is None:
                critical("'test_func_msg' is only applicable together with "
                         f"'test_func' ({self.get_path()}).")
            if not (isinstance(test_func_msg, str) and test_func_msg.strip()):
                critical(f"As value for test_func_msg, {test_func_msg} had "
                         "to be a string object.")
            self._ui_props["test_func_msg"] = test_func_msg.strip()

        if isinstance(self._children, dict):
            if self._item_decl is None:
                self._expand_by_type_decl(type_decl)
            else:
                lt = CvvPathElem(self, self.LIST_ITEM_TEMPLATE_ID,
                                 self._item_decl)
                lt._cur_val.validate_list_keys()
                self._ui_props["item_template"] = lt
                if not self._expand_by_list_value():
                    critical(f"Incompatible list value for {self.get_path()}.")
