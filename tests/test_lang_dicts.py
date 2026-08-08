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

# The strings this library writes itself, in DECL_LANG. Read off the singleton
# rather than listed here, so that a display string added to the editor cannot
# be forgotten: it lands in this set by being registered at all.
LIB_KEYS = {key for key, lang in config_mgr._xlation_langs.items()
            if lang == ConfigManager.DECL_LANG}


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
    # Not "every dictionary holds the same keys": DECL_LANG needs no dictionary
    # for its own strings, and a dictionary is free to carry a host's keys too
    # -- the appliance this grew from ships its German ones here. What has to
    # hold is that no language is missing part of the editor.
    dicts = _shipped()
    assert dicts, "no dictionaries ship with the package"
    for lang, d in dicts.items():
        if lang == ConfigManager.DECL_LANG:
            continue
        missing = sorted(LIB_KEYS - set(d))
        assert not missing, (
            f"'{lang}' cannot render the editor: {len(missing)} strings "
            f"missing, e.g. {missing[:3]}")


def test_the_reference_language_ships_no_translation_of_itself():
    # An entry mapping one of its own keys would be a translation from English
    # into English -- harmless but meaningless, and a sign that a flip of the
    # source language was only half done.
    d = _shipped().get(ConfigManager.DECL_LANG, {})
    own = sorted(LIB_KEYS & set(d))
    assert not own, f"'{ConfigManager.DECL_LANG}' translates itself: {own[:3]}"


def test_no_entry_is_left_empty():
    # An empty value is what "untranslated" looks like once the entry exists,
    # and a shipped dictionary has no business carrying one.
    for lang, d in _shipped().items():
        blank = sorted(k for k, v in d.items()
                       if isinstance(v, str) and not v.strip())
        assert not blank, f"'{lang}' has empty translations: {blank[:5]}"


def test_each_dictionary_declares_its_format():
    # Without the stamp the loader takes the file for an older format and
    # migrates it, which drops every entry that reads like its key -- exactly
    # the ones that say "this string is taken over unchanged".
    for lang, d in _shipped().items():
        assert d.get(ConfigManager.LANG_FORMAT_KEY) == ConfigManager.LANG_FORMAT, (
            f"'{lang}' is missing the current format marker")
