"""An option marked verbatim is a name, not prose: its label is no
translation key, whether a provider delivers the option or a declaration
lists it (0.48.1)."""

from gpsmcpmms import config_mgr

DECL = {"where": {"type": "enum", "label": "Country of the verbatim test",
                  "values": {"XQ": {"label": "XQ", "verbatim": True,
                                    "tooltip": "Tooltip of the verbatim test"},
                             "XR": {"label": "Prose option of the verbatim test"}}}}
SAID = {"Country of the verbatim test", "Tooltip of the verbatim test",
        "Prose option of the verbatim test", "XQ"}


def test_a_declared_verbatim_option_is_no_translation_key(setup_demo_environment):
    before = set(config_mgr._active_xlation_keys)
    try:
        config_mgr._harvest_xlation_keys(DECL)
        keys = config_mgr._active_xlation_keys
        assert "XQ" not in keys
        assert SAID - {"XQ"} <= keys
    finally:
        config_mgr._active_xlation_keys -= (SAID - before)
