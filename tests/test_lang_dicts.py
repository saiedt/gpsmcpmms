"""The shipped dictionaries are what makes the editor readable in a language.

They are seeded onto every device and, from there, are what the translation
template is cut from. A key one language has and another lacks is therefore not
a cosmetic difference: it is a string somebody will be asked to translate in one
language and never in the other.
"""

import json
import os

import gpsmcpmms
from gpsmcpmms import config_mgr
from gpsmcpmms.config import ConfigManager

LANG_DIR = os.path.join(os.path.dirname(gpsmcpmms.__file__), "ui", "lang")

# The strings this library writes itself. Read off the singleton rather than
# listed here, so that a display string added to the editor cannot be forgotten:
# it lands in this set by being registered at all. No host has registered
# anything at this point, so what stands there is the library's own -- the
# editor's chrome *and* its three own parameters, which OWN_UI_KEYS alone would
# have missed.
LIB_KEYS = set(config_mgr._active_xlation_keys)


def _shipped():
    dicts = {}
    for name in sorted(os.listdir(LANG_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(LANG_DIR, name), encoding="utf-8") as f:
            dicts[name[:-len(".json")]] = json.load(f)
    return dicts


def test_the_library_knows_its_own_strings():
    assert LIB_KEYS, "no display strings registered for this library itself"


def test_every_language_renders_the_whole_editor():
    # Half the release gate: a shipped dictionary that is short of a string
    # leaves that part of the editor reading in DECL_LANG, on every device the
    # release reaches.
    dicts = _shipped()
    assert dicts, "no dictionaries ship with the package"
    for lang, d in dicts.items():
        missing = sorted(LIB_KEYS - set(d))
        assert not missing, (
            f"'{lang}' cannot render the editor: {len(missing)} strings "
            f"missing, e.g. {missing[:3]}")


def test_no_dictionary_carries_anything_but_this_library():
    # The other half, and the one that had to be learnt. These files are the
    # starting kit of every fresh deployment, so whatever stands in them is
    # handed to strangers: a while ago they carried the whole H4H appliance,
    # including the service catalogue of somebody's business, and any adopter
    # would have found "Begleitung -> Companionship" in their dictionaries.
    #
    # A host's translations belong to the host's own image. This library ships
    # its own strings and nothing else.
    for lang, d in _shipped().items():
        foreign = sorted(set(d) - LIB_KEYS - set(ConfigManager.RESERVED_LANG_KEYS))
        assert not foreign, (
            f"'{lang}' carries {len(foreign)} keys this library never "
            f"registers, e.g. {foreign[:3]}")


def test_the_reference_language_ships_no_dictionary_at_all():
    # The keys are already written in it. A file repeating each of them after
    # itself would be ballast that every change had to maintain twice, and the
    # completeness count says so too: DECL_LANG is complete by construction.
    assert ConfigManager.DECL_LANG not in _shipped(), (
        f"'{ConfigManager.DECL_LANG}' ships a translation of itself")


def test_no_entry_is_left_empty():
    # An empty value is what "untranslated" looks like once the entry exists,
    # and a shipped dictionary has no business carrying one.
    for lang, d in _shipped().items():
        blank = sorted(k for k, v in d.items()
                       if isinstance(v, str) and not v.strip())
        assert not blank, f"'{lang}' has empty translations: {blank[:5]}"


def test_each_dictionary_names_its_language():
    # A dictionary says what its language calls itself, and nothing else will:
    # this library keeps no table of endonyms, and a deployment that ships no
    # languages.json has nowhere else to look. Without the entry the language
    # selector shows a bare code.
    #
    # This replaced a test demanding a format stamp. The stamp guarded a
    # migration away from a dictionary shape that no longer exists anywhere,
    # and went with it.
    for lang, d in _shipped().items():
        name = d.get(ConfigManager.LANG_NAME_KEY)
        assert isinstance(name, str) and name.strip(), (
            f"'{lang}' does not say what its language is called")
