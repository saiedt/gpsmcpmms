"""The shipped dictionaries are the manifest of what a device class says.

They are seeded onto every device and, from there, are what the translation
template is cut from. A key that one language has and another lacks is
therefore not a cosmetic difference: it is a string somebody will be asked to
translate in one language and never in the other.
"""

import json
import os

import gpsmcpmms
from gpsmcpmms.config import ConfigManager

LANG_DIR = os.path.join(os.path.dirname(gpsmcpmms.__file__), "ui", "lang")


def _shipped():
    dicts = {}
    for name in sorted(os.listdir(LANG_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(LANG_DIR, name), encoding="utf-8") as f:
            dicts[name[:-len(".json")]] = json.load(f)
    return dicts


def test_every_language_covers_the_same_keys():
    dicts = _shipped()
    assert dicts, "no dictionaries ship with the package"
    reserved = set(ConfigManager.RESERVED_LANG_KEYS)
    sets = {lang: set(d) - reserved for lang, d in dicts.items()}
    reference = sets[sorted(sets)[0]]
    for lang, keys in sets.items():
        assert keys == reference, (
            f"'{lang}' differs: only there "
            f"{sorted(keys - reference)[:5]}, missing "
            f"{sorted(reference - keys)[:5]}")


def test_no_entry_is_left_empty():
    # An empty value is what "untranslated" looks like once the entry exists,
    # and a shipped dictionary has no business carrying one.
    for lang, d in _shipped().items():
        blank = sorted(k for k, v in d.items()
                       if isinstance(v, str) and not v.strip())
        assert not blank, f"'{lang}' has empty translations: {blank[:5]}"


def test_each_dictionary_declares_its_format():
    # Without the stamp the loader takes the file for an older format and
    # migrates it, which drops every entry that reads like its German key --
    # exactly the ones that say "this string is taken over unchanged".
    for lang, d in _shipped().items():
        assert d.get(ConfigManager.LANG_FORMAT_KEY) == ConfigManager.LANG_FORMAT, (
            f"'{lang}' is missing the current format marker")
