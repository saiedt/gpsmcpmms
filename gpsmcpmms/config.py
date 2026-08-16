#!/usr/bin/env python3
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

import csv
import hashlib
import hmac
import inspect
import io
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
from .cvv_tree import CvvError, CvvNode


class ConfigManager:
    FACTORY_DEFAULT_PASSWD = "4a3d2m1N"
    API_HEADER = "X-GPSMCPMMS-Api"
    TOKEN_HEADER = "X-GPSMCPMMS-Token"
    CAPTURE_TIMEOUT = 30    # seconds; see spec 4.9.3
    # deploy-time settings, read from the environment (see _env_int), not the
    # cvv tree: GPSMCPMMS_UI_PORT / GPSMCPMMS_SESSION_TIMEOUT override these
    DEFAULT_UI_PORT = 8080
    DEFAULT_SESSION_TIMEOUT = 30    # minutes
    # config_mgr's own module holds only ui_passwd (an editable, persisted
    # param); it is handled by config_mgr itself and is therefore never
    # rendered as an editable module in the config-editor
    OWN_MODULE_ID = "config"
    # how many existing languages may be included as reference columns in a
    # downloaded translation template (context for the translator/AI)
    MAX_TEMPLATE_REFS = 3
    # The language a display string is *written* in when it reaches this
    # library: the key language. A key is its own fallback, so whatever is not
    # translated is shown in this language.
    #
    # English, because this is a public library: a German key set would oblige
    # anyone adopting it to write German labels and translate them into their
    # own language. Every key in the tree is written in it, this library's and
    # every host's alike -- a module could once declare its own in another
    # language, and the cost was a second source column in every template, a
    # key set no longer comparable as strings, and a fallback that could put a
    # word of a third language on the screen. What a module receives in a
    # foreign language it settles into DECL_LANG and hands the original over
    # through add_original_xlations().
    DECL_LANG = "en"
    # The template's first column holds the keys. It was called "de" when that
    # was the only possibility, then "key"; a file still carrying either header
    # uploads unchanged, because a header the upload does not recognise falls
    # back to the first column.
    KEY_COLUMN = "key"
    # What a display string is, as far as it changes how it gets translated --
    # not where it came from. A label has to stay short because it sits beside
    # a field; a tooltip may be a whole sentence; a placeholder is usually a
    # format example that is taken over as it is; a spoken text is read by a
    # voice, where an abbreviation or a stray parenthesis is heard rather than
    # seen; and the editor's own chrome is none of those.
    XLATION_KINDS = ("label", "tooltip", "placeholder", "speech", "ui")
    # which of them a Declaration key produces. A button caption is a label --
    # same constraint, same brevity -- and the explanatory ones are tooltips
    # whatever they are called.
    DECL_KEY_KINDS = {
        "label": "label", "acquire_button": "label",
        "tooltip": "tooltip", "hint": "tooltip", "test_func_msg": "tooltip",
        "placeholder": "placeholder",
    }
    # bookkeeping a translation dictionary carries beside its translations;
    # never a key anybody translates
    LANG_FORMAT_KEY = "lang_format"
    # What this dictionary's language calls itself. It lives here rather than
    # in languages.json because the name belongs to the language, not to the
    # list of languages somebody permits -- a deployment that permits
    # everything still has to be able to write "Português" under the dropdown.
    LANG_NAME_KEY = "lang_name"
    RESERVED_LANG_KEYS = ("lang_cache_modified", LANG_FORMAT_KEY,
                          LANG_NAME_KEY)
    # 2: an absent entry means untranslated, and an entry that reads like the
    # German means a translator decided it stays that way. Until 1 every known
    # key was present in every dictionary as its own value, and that was how
    # "untranslated" was written down -- which left no way at all to say that a
    # word is simply the same in both languages.
    LANG_FORMAT = 2

    # Which languages a deployment may keep dictionaries for at all -- the
    # first of the two handles over that choice.
    #
    # Names, not permission. This table answers "what does this language call
    # itself", so that a dropdown reads Deutsch and Türkçe rather than de and
    # tr; it permits nothing and forbids nothing.
    #
    # It was both once, and being both was the mistake. It was written to
    # <ui_dir>/languages.json on first start, and a deployment thereby
    # acquired an upper bound it had never chosen -- sitting in its own
    # release assets, looking like its own decision. Which languages exist in
    # a deployment is the hosting application's to settle, by shipping that
    # file or by registering a validator; see set_language_validator().
    #
    # The entries are not invented: they are what Google Cloud Text-to-Speech
    # answered on 2026-08-02 when asked which languages it has voices for.
    # That origin is now no more than an accident of how the table was first
    # filled -- as a list of endonyms it is simply incomplete, and a language
    # missing from it costs only its name, which whoever adds it types in.
    # Persian is absent for that reason and no other: the speech service
    # refuses fa-IR outright, which was a reason for one appliance to refuse
    # it, never a reason for this library to.
    LANGUAGE_OPTIONS = {
        "af": "Afrikaans", "am": "አማርኛ", "ar": "العربية", "bg": "Български",
        "bn": "বাংলা", "ca": "Català", "cmn": "普通话", "cs": "Čeština",
        "da": "Dansk", "de": "Deutsch", "el": "Ελληνικά", "en": "English",
        "es": "Español", "et": "Eesti", "eu": "Euskara", "fa": "فارسی",
        "fi": "Suomi", "fil": "Filipino", "fr": "Français", "gl": "Galego",
        "gu": "ગુજરાતી",
        "he": "עברית", "hi": "हिन्दी", "hr": "Hrvatski", "hu": "Magyar",
        "id": "Bahasa Indonesia", "is": "Íslenska", "it": "Italiano",
        "ja": "日本語", "kn": "ಕನ್ನಡ", "ko": "한국어", "lt": "Lietuvių",
        "lv": "Latviešu", "ml": "മലയാളം", "mr": "मराठी",
        "ms": "Bahasa Melayu", "nb": "Norsk bokmål", "nl": "Nederlands",
        "pa": "ਪੰਜਾਬੀ", "pl": "Polski", "pt": "Português", "ro": "Română",
        "ru": "Русский", "sk": "Slovenčina", "sl": "Slovenščina",
        "sr": "Српски", "sv": "Svenska", "sw": "Kiswahili", "ta": "தமிழ்",
        "te": "తెలుగు", "th": "ไทย", "tr": "Türkçe", "uk": "Українська",
        "ur": "اردو", "vi": "Tiếng Việt", "yue": "粵語",
    }
    # what a single upload for a 'file' parameter may weigh. Ring tones and
    # announcements are measured in kilobytes; the limit is here because an
    # editor that accepts unbounded uploads can fill an appliance's SD card
    # from the browser.
    MAX_UPLOAD_BYTES = 8 * 1024 * 1024
    # deliberately beside the staged web assets rather than in ui_dir/lang/:
    # everything ending in .json down there is loaded as a dictionary, and a
    # file named languages.json would become a language called "languages"
    LANGUAGE_FILE = "languages.json"
    # how long one reachability probe of a 'pingable' parameter may take
    PING_TIMEOUT = 2
    # the editor's web assets, and the record of what was staged into ui_dir
    WEB_ASSETS = ("index.html", "style.css", "app.js")
    ASSET_STAMP = ".staged.json"
    # column separator of the translation CSVs: a pipe is chosen because it is
    # very unlikely to occur inside a German key or a translation, so cells
    # never need quoting and no delimiter collision can arise
    CSV_DELIMITER = "|"

    # German display strings internal to config.py and its editor; they act
    # as keys into the translation dictionaries (spec 4.3)
    # The editor's own display strings, in the language this library is written
    # in. They are keys like any other, so a deployment that wants the editor in
    # German takes it from the shipped de.json -- see DECL_LANG.
    OWN_UI_KEYS = (
        "Hub4Help Configuration Editor",
        "Save", "Apply", "Remove", "Undo",
        "End session", "Show protected parameters",
        "Exit admin mode", "Language",
        "Incorrect password",
        "Read-only mode: another session is active",
        # Without the admin password only waiting is left, and until now
        # nobody was told what for. {time} is the earliest the lock falls by
        # itself -- earliest, because the holder pushes it out by carrying on
        # working, which is why the sentence says "after" and names no
        # deadline.
        "Alternatively, without an admin password: renewed access "
        "after {time}.",
        "Take over session", "Session taken over",
        "The device is still using the factory default password",
        "Invalid input", "Apply failed",
        # What is left to say when a request comes back without a reason the
        # editor can show. It claimed "connection lost" once, which is a
        # diagnosis: the device was reachable throughout, and the sentence
        # sent somebody looking for a fault in the wrong place. This one says
        # only what is known, and it stays true where the connection really
        # has gone.
        "No answer from the device.",
        "OK", "Cancel", "Saved", "Rejected", "Test", "New",
        "Password", "New password",
        "Reading value...", "Value applied", "Timeout",
        "Really remove this entry?", "List is full",
        "These options were never set; apply them as “no”/“disabled”?",
        "Too few entries in", "Reload",
        # How a test came out, in three grades: never started, ran, ran but
        # could not carry the test out. "Successful" stood here once and
        # promised too much -- what a test was worth is heard and seen only by
        # whoever is standing in front of the device.
        "The test could not be started.",
        "The test routine ran without errors.",
        "The test routine could not carry out the test.",
        "Check", "Check failed",
        # What is left to show when a provider of the hosting application
        # raises. The exception itself goes to the log, where it belongs; the
        # editor says only that the answer failed to arrive, because a
        # traceback in a hint line helps nobody standing at the device.
        "Internal error while determining the values",
        "Internal error while establishing the hint",
        "Reachable", "no response to ping", "Name cannot be resolved",
        "File exists", "Folder exists", "Path does not exist",
        "Does not exist yet, can be created",
        # Translation management. Two verbs rather than one noun: "manage"
        # never said whether you were about to add or to improve, and the
        # panel looked identical either way.
        "Add new translation", "Edit existing translation",
        "New language", "Language code", "Language name", "Editing",
        "Translating the source keys, with up to 3 languages as further "
            "context (please choose):",
        "Translation file: start by", "then", "finally",
        "Download CSV", "Select completed CSV",
        "Upload the selected CSV",
        "No translation exists yet", "translated", "Translation processed", "Invalid file",
        "Value already taken",
        "Choose file", "File type not allowed",
        "File name not allowed", "File too large",
        # a hint states something about the present; without the moment it was
        # established it would keep asserting it long after it stopped being so
        "As of", "Refresh",
    )

    # Declaration keys whose string values are German display strings and
    # hence translation keys
    XLATION_DECL_KEYS = (
        "acquire_button", "hint", "label", "placeholder", "test_func_msg",
        "tooltip"
    )

    # ------------------------------------------------------------------
    # Singleton enforcement
    # ------------------------------------------------------------------
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------
    def __init__(self):
        if self._initialised:
            return
        self._lock = threading.Lock()
        self._initialised = True

        # Initialize the internal logger reference with a clean bootstrap default
        self._logger = logging.getLogger("GPSMCPMMS_Bootstrap")
        self._logger_explicitly_set = False
        
        if not self._logger.handlers:
            _bootstrap_handler = logging.StreamHandler()
            _bootstrap_handler.setFormatter(logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] (%(module)s): %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._logger.addHandler(_bootstrap_handler)
            self._logger.setLevel(logging.DEBUG)

        # Read system configurations via environment variables
        # with secure local fallbacks
        self.cvv_dir = os.path.abspath(os.environ.get("GPSMCPMMS_CVV_DIR",
                                os.path.expanduser("~/.config/gpsmcpmms/cvv")))
        self.ui_dir = os.path.abspath(os.environ.get("GPSMCPMMS_UI_DIR",
                                os.path.expanduser("~/.config/gpsmcpmms/ui")))

        # Ensure runtime environments exist securely on the file system
        os.makedirs(self.cvv_dir, exist_ok=True)
        os.makedirs(self.ui_dir, exist_ok=True)

        # Load the translation dictionaries (spec 4.3)
        self._init_lang_support()

        # Central registries: keyed by module_id
        self._callback_registry: dict = {}
        self._func_registry: dict = {}
        # the language each module writes its display strings in; a tree may
        # hold modules that do not agree, which is why it is per module

        # exclusive editing session of the config-editor (spec 4.8)
        self._session_token = None
        self._session_expires = 0.0
        self._session_admin = False
        # who holds it, purely so the log can say whom to go and ask; a
        # read-only editor is otherwise an unexplained state on the screen
        self._session_owner = None
        self._editor_started = False
        # The key set as it stood when the editor started, or None while it has
        # not. See _note_xlation_key() for what it is compared against.
        self._keys_at_start = None
        self._flask_app = None

        # long-polling requests waiting for backend-captured values,
        # keyed by the absolute path of the target param (spec 4.9.3)
        self._capture_waiters = {}

        # initialize cvv and own config params
        self._cvv_root = CvvNode.register(self, self.cvv_dir)
        CvvNode.set_logger(self, self._logger)
        own_decl = { "type": self.OWN_MODULE_ID,
                     "label": "Configuration service" }
        own_types = { self.OWN_MODULE_ID: {
                "ui_passwd": {
                    "type": "password", "label": "UI password",
                    "protected": True,
                    "default_val": self.FACTORY_DEFAULT_PASSWD,
                    "tooltip": "Administrator password for unlocking "
                             + "protected parameters."
                }
            }}
        self._harvest_xlation_keys(own_decl)
        self._harvest_xlation_keys(own_types)
        my_config = CvvNode.init_module(self, self.OWN_MODULE_ID,
                                        own_decl, own_types)
        if not isinstance(my_config, dict):
            my_config = {}
        self._ui_passwd = (my_config.get("ui_passwd") or
                           self.FACTORY_DEFAULT_PASSWD)
        # ui_port and session_timeout are deploy-time settings, read from the
        # environment like GPSMCPMMS_CVV_DIR / _UI_DIR (not editable params).
        self._ui_port = self._env_int("GPSMCPMMS_UI_PORT", self.DEFAULT_UI_PORT,
                                      minimum=1, maximum=65535)
        self._session_timeout = self._env_int(
                "GPSMCPMMS_SESSION_TIMEOUT", None, minimum=1, maximum=1440)
        
        self._logger.debug("ConfigManager persistence layer and environment "
                           "successfully initialized.")

    # ------------------------------------------------------------------
    # API
    #
    # - for the main app: switch_to_app_logger(logger)
    #                     to inject application specific logger
    # - for importers of config_mgr: config_ready, protected_params_ready,
    #                                query, register_params, and
    #                                handle_value_event
    # - for the config-editor layer: _apply_module_update,
    #                                _resolve_backend_func, and _may_access
    # - for frontend: the REST-API set up by start_editor()
    # ------------------------------------------------------------------
    def switch_to_app_logger(self, logger: logging.Logger) -> None:
        """
        Injects the production-grade application logger. 
        Can only be called once per application runtime lifecycle.
        """
        if self._logger_explicitly_set:
            raise RuntimeError("Application logger has already been registered "
                               "and locked.")
        
        if not isinstance(logger, logging.Logger):
            raise TypeError("Injected logger must be an instance of "
                            "logging.Logger.")
            
        self._logger = logger
        CvvNode.set_logger(self, logger)
        self._logger_explicitly_set = True
        self._logger.debug("GPSMCPMMS engine successfully attached to "
                           "production application logger.")

    def config_ready(self, path=None):
        return CvvNode.config_ready(self, path)

    def protected_params_ready(self):
        return CvvNode.protected_params_ready(self)

    def query(self, path):
        return CvvNode.query(self, path)

    def register_params(self, module_id, module_label, param_dict,
                        callback, type_dict=None, module_tooltip=None,
                        func_dict=None):
        if not (module_id and isinstance(module_id, str) and
                not module_id in self._callback_registry
        ):
            raise ValueError(f"Invalid or redundant module id: {module_id}.")
        if not callable(callback):
            raise ValueError(
                f"register_params(): 'callback' must be callable "
                f"(got {type(callback).__name__})."
            )
        if func_dict is not None and not (
                isinstance(func_dict, dict) and
                all(isinstance(k, str) and k and callable(v)
                    for k, v in func_dict.items())
        ):
            raise ValueError("register_params(): 'func_dict' must map "
                             "function names to callables.")
        self._callback_registry[module_id] = callback
        self._func_registry[module_id] = func_dict or {}
        if isinstance(module_label, str) and module_label.strip():
            self._note_xlation_key(module_label.strip(), "label")
        if isinstance(module_tooltip, str) and module_tooltip.strip():
            self._note_xlation_key(module_tooltip.strip(), "tooltip")
        self._harvest_xlation_keys(param_dict, self._func_registry[module_id])
        self._harvest_xlation_keys(type_dict, self._func_registry[module_id])
        self._check_values_for(param_dict, self._func_registry[module_id])
        self._check_values_for(type_dict, self._func_registry[module_id])
        type_registry = type_dict if isinstance(type_dict, dict) else {}
        type_registry[module_id] = param_dict
        config_value = CvvNode.init_module(self, module_id, {
                "label": module_label,
                "tooltip": module_tooltip,
                "type": module_id
            }, type_registry)
        # any runtime schema change invalidates the exclusive editing
        # token, forcing the config-editor to re-align (spec 4.8)
        self._invalidate_session(f"module '{module_id}' registered its "
                                 "parameters")
        callback(config_value)

    def discard_module(self, module_id):
        """
        Declares that a module has no parameters any more, and removes every
        trace of the ones it used to have. Returns True when there was
        something to remove.

        Called by a module that can tell it is past needing them -- instead of
        register_params, or later in the same run, whenever that becomes
        apparent. The appliance case is a provisioning key: it has to exist
        while a distributor prepares a device class, and must not exist on the
        devices cloned from it afterwards. Hiding the field would not do --
        what matters is that the value is off the card, and only deleting the
        persisted data achieves that, since the declaration would otherwise
        restore it at the next start.

        Not a registration with an empty parameter dict, although that would
        have been less to write. An empty dict is a shape a module can arrive
        at by accident, and the effect here is the loss of everything a module
        had stored: for the telephony module that would be the credentials of
        the public line. A destructive step should take a sentence that could
        not have been written by mistake.
        """
        if not (module_id and isinstance(module_id, str)):
            raise ValueError(f"Invalid module id: {module_id}.")
        module_id = module_id.strip()
        removed = CvvNode.discard_module(self, module_id)
        self._callback_registry.pop(module_id, None)
        self._func_registry.pop(module_id, None)
        if removed:
            # the schema changed, so the editor's picture of it is stale
            self._invalidate_session(f"module '{module_id}' discarded its "
                                     "parameters")
            self._logger.info(f"Module '{module_id}' discarded its parameters "
                              "and everything stored for them.")
        return removed

    def note_xlation_keys(self, *keys, kind=None):
        """
        Registers display strings that do not originate from a Declaration --
        typically texts a module speaks or shows at runtime. Without this they
        would never reach a translation template, and the cleanup would treat
        them as orphans. Call once per run, next to register_params().

        `kind` says what these strings are, and appears in the translation
        template beside them (see XLATION_KINDS). Worth passing "speech" above
        all: nothing else in the file could tell a translator that a sentence
        will be read aloud rather than shown, and the two are not translated
        the same way. A Declaration says it by itself; only a runtime string
        has to be told.

        The strings are DECL_LANG, like every key. A module whose wording
        arrives in another language settles on a DECL_LANG one, notes that
        here, and hands the original over through add_original_xlations().
        """
        if kind is not None and kind not in self.XLATION_KINDS:
            raise ValueError(f"note_xlation_keys(): unknown kind {kind!r}; "
                             f"expected one of {sorted(self.XLATION_KINDS)}.")
        for key in keys:
            if isinstance(key, str) and key.strip():
                self._note_xlation_key(key.strip(), kind)

    def add_original_xlations(self, xlation_lang, xlations):
        """Supplies translations for already noted keys, from where they came.

        `xlations` maps each key to its reading in `xlation_lang`. The keys must
        already be registered -- through a Declaration or note_xlation_keys();
        this call adds nothing to the key set, only to a dictionary.

        The case it is for: a key that is itself a translation. A module may
        take its display strings from somewhere else -- the categories of a
        remote catalogue, the fields of a foreign schema -- and such a string
        arrives in whatever language its source speaks. Registering it as it
        stands would make a key in that language, which is the one thing this
        library cannot represent: the completeness count would call it
        translated for a language it is merely written in, a reader of
        DECL_LANG would be shown a word from another one, and nothing in a
        template would say which row is which. So the module settles on a
        DECL_LANG wording and notes that as the key -- and then the original is
        the better translation than anything derived back out of it, because it
        is what somebody actually wrote.

        Three rules, and each of them is there for a reason:

        * **An existing translation is never touched.** These are starting
          points, not corrections; otherwise every restart would flatten the
          work of whoever improved on the wording the source happened to use.
        * **A language nothing has a dictionary for is not created here.** One
          would otherwise become a supported language on the strength of a
          handful of entries, and a host offering its users exactly the
          supported languages would start offering it.
        * **Keys nobody registered are refused.** An entry for a key the
          software does not use is an orphan the moment it is written, and it
          would then be offered to a translator as work.
        """
        lang = (xlation_lang.strip().split("-")[0]
                if isinstance(xlation_lang, str) else "")
        if not lang:
            raise ValueError("add_original_xlations(): 'xlation_lang' must "
                             "name the language these readings are in.")
        if lang == self.DECL_LANG:
            raise ValueError(
                    f"add_original_xlations(): {lang!r} is the language the "
                    f"keys are already written in; there is nothing to add.")
        if not isinstance(xlations, dict):
            raise ValueError("add_original_xlations(): 'xlations' must map each "
                             "key to its reading in that language.")

        with self._lock:
            book = self._lang_cache.get(lang)
            if book is None:
                self._logger.info(
                        f"No dictionary for '{lang}': {len(xlations)} original "
                        f"reading(s) not recorded. A language is not created by "
                        f"supplying readings for it.")
                return
            added = unknown = 0
            for key, reading in xlations.items():
                if not (isinstance(key, str) and key.strip()):
                    continue
                key = key.strip()
                if key not in self._active_xlation_keys:
                    unknown += 1
                    continue
                if not (isinstance(reading, str) and reading.strip()):
                    continue
                if isinstance(book.get(key), str) and book[key]:
                    continue            # somebody already said it better
                book[key] = reading.strip()
                added += 1
        if unknown:
            self._logger.warning(
                    f"{unknown} original reading(s) for '{lang}' name keys that "
                    f"are not registered; they were refused. Note the keys "
                    f"before supplying their readings.")
        if added:
            self._logger.debug(
                    f"{added} original reading(s) recorded for '{lang}'.")

    def _load_language_options(self):
        """The application's list of permitted languages, or None if it keeps
        none.

        <ui_dir>/languages.json belongs to the hosting application, and this
        library neither ships it nor creates it. It used to be seeded here
        from LANGUAGE_OPTIONS whenever it was missing, and that was wrong
        twice over: a deployment ended up with a list it never chose, and the
        file then looked like the application's decision in its own release
        assets. One appliance carried fifty-five languages that way, none of
        them meant.

        Absent is therefore an answer and not a gap. It means the application
        imposes no upper bound, and whoever administers the device may name a
        language of their own -- subject to a validator, if one is registered.

        A file that cannot be read is treated as absent, loudly. A bound this
        library cannot make out is one it cannot honour, and hiding languages
        the device holds dictionaries for would take the end customer's own
        language out of the selector -- a worse failure than allowing one more
        than somebody intended.
        """
        path = os.path.join(self.ui_dir, self.LANGUAGE_FILE)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                options = json.load(f)
            if not (isinstance(options, dict) and options and all(
                        isinstance(k, str) and isinstance(v, str)
                        for k, v in options.items())):
                raise ValueError("not a non-empty object of strings")
        except (OSError, ValueError) as exc:
            self._logger.error(
                    f"'{path}' unusable ({exc}); this deployment is treated as "
                    f"one that names no permitted languages. Every dictionary "
                    f"present stays selectable.")
            return None
        return options

    def set_language_name(self, lang, name):
        """Records what a language is called, and keeps it.

        Anyone adding a language this release has no name for has to say what
        it is called, because the editor shows names and never codes: a row
        reading "ps" tells a deployer nothing, and a translator even less.

        The name goes into the dictionary it names, under a reserved key --
        not into languages.json. That file states which languages the
        application permits, and writing to it here would turn a deployment
        that permits everything into one that permits exactly what somebody
        happened to add. Where the application does keep a list, the name is
        in it already and there is nothing to record.
        """
        if not (isinstance(lang, str) and lang.strip() and
                isinstance(name, str) and name.strip()):
            return False
        lang, name = lang.strip(), name.strip()
        with self._lock:
            book = self._lang_cache.get(lang)
            if book is None:
                return False
            if book.get(self.LANG_NAME_KEY) == name:
                return True
            book[self.LANG_NAME_KEY] = name
            book["lang_cache_modified"] = True
        return True

    def language_name(self, lang):
        """What to call a language on screen; the code itself only as a last
        resort, and that is a gap somebody should fill.

        Three places, in the order of who knows best: the dictionary's own
        record of its name, then the application's list of permitted
        languages, then the endonyms this release happens to know.
        """
        with self._lock:
            book = self._lang_cache.get(lang)
            own = book.get(self.LANG_NAME_KEY) if isinstance(book, dict) else None
        if isinstance(own, str) and own.strip():
            return own.strip()
        if self._language_options and lang in self._language_options:
            return self._language_options[lang]
        return self.LANGUAGE_OPTIONS.get(lang, lang)

    def set_language_validator(self, validator):
        """The *other* way for an application to bound the languages: judge
        each one as it is named, rather than list them in advance.

        `validator` takes a language code and returns whether it is
        acceptable; None withdraws it. An application knows things this
        library cannot -- whether a speech service has a voice for a language,
        say, since one a device can display but never speak is only half a
        language on a device that reads aloud.

        The two ways are alternatives, not layers. Where the application ships
        <ui_dir>/languages.json, that file is the whole answer and a validator
        is never asked: the list already says which languages exist here, and
        putting a second opinion behind it would mean an entry somebody wrote
        down could still be refused, with nothing on screen to say why. A
        validator therefore governs exactly the case the list does not cover --
        a language an administrator names that nobody listed in advance.

        A validator that raises is treated as a yes. Refusing to configure a
        device because a check itself is broken would be the worse failure,
        and the protected languages are accepted regardless: DECL_LANG is what
        every other dictionary is written against.
        """
        self._language_validator = validator if callable(validator) else None

    def language_options(self):
        """The languages the application permits, as {code: endonym}, or None
        where it permits any.

        Not the ones this deployment *has* -- that is supported_languages().
        """
        return (dict(self._language_options)
                if self._language_options is not None else None)

    def protected_langs(self):
        """The languages that cannot be discarded: DECL_LANG, and nothing else.

        Every key is written in it and every dictionary is written against it,
        so a deployment without it has no source to translate from. It is a
        tuple rather than a single code because callers ask "is this language
        protected", and because for a while the answer was longer: a module
        could declare its keys in a language of its own, and that language had
        to be protected too. Hosts settle on DECL_LANG now, so one entry is the
        whole answer.
        """
        return (self.DECL_LANG,)

    def _language_allowed(self, lang):
        # One gate or the other, never both. A list settles the question by
        # itself, and a validator only gets asked where there is no list --
        # see set_language_validator() for why layering them would leave an
        # administrator staring at a refusal with nothing to explain it.
        if lang in self.protected_langs():
            return True
        if self._language_options is not None:
            return lang in self._language_options
        if self._language_validator is None:
            return True
        try:
            return bool(self._language_validator(lang))
        except Exception as exc:
            self._logger.error(
                    f"The host's language validator raised on '{lang}': "
                    f"{exc}. Treating the language as acceptable.")
            return True

    def supported_languages(self):
        """
        The languages this deployment can be read in: those a dictionary exists
        for *and* the allow-list names. DECL_LANG is always among them, with or
        without a dictionary -- it needs none, the keys are already in it.

        A host application that addresses its users in one of these -- the
        H4H appliance reads its announcements aloud -- has to offer exactly
        this set and no more. Offer a language the dictionaries do not cover
        and translate() falls back to the key without saying so: the text would
        be read in the wrong language by a voice from the right one, and
        nothing in the log would explain it.

        Where the application keeps a list, it has to be part of the answer
        and not just of what an upload may add. A release ships dictionaries
        for its own strings, and a fresh deployment starts from those;
        without this, every language the package happens to carry would turn
        up in the editor's language menu, covered for this library's own
        chrome and untranslated for everything the application declares.
        Whoever writes the list expects it to be the last word on which
        languages exist here -- and a dictionary standing by for a language
        nobody permits costs nothing and is ready the day somebody does.

        Where the application keeps none, the dictionaries are the whole
        answer: nothing bounds them, so nothing narrows them either.

        A validator does not narrow this set, and the difference from a list
        is deliberate. A list is a standing statement about which languages
        exist here, cheap to consult for every dictionary present. A validator
        is a judgement made on the spot, possibly over the network, and asking
        it once per language on every call would be both slow and fragile --
        an unreachable service would answer "acceptable" for everything, which
        is how the old arrangement quietly stopped bounding anything. So a
        validator guards admission, not what has already been admitted: it
        decides whether a language may be added, and a dictionary that exists
        stays readable.
        """
        with self._lock:
            present = set(self._lang_cache)
            allowed = (None if self._language_options is None
                       else set(self._language_options))
        if allowed is not None:
            present &= allowed
        return sorted(present | set(self.protected_langs()))

    def translation_status(self, lang, keys=None):
        """
        How many display strings have a real translation in `lang`, and how
        many there are altogether -- as (done, total).

        `keys` narrows the question to a subset, which is what makes the
        answer useful to a host: "are the service names translated" is a
        different question from "is anything left to translate", and only the
        host knows which strings are its service names.

        An entry counts as soon as it is there, whatever it says. Absence is
        what "not translated yet" looks like -- nothing is written into a
        dictionary until somebody translates -- which leaves an entry reading
        like its key free to mean the opposite: that this string was looked at
        and stays. Without that, "OK" in Polish was inexpressible and kept its
        language incomplete for ever.

        DECL_LANG is complete by construction, with or without a dictionary:
        the keys are already written in it, and a file repeating each of them
        after itself would be ballast that every change had to maintain twice.
        """
        with self._lock:
            active = set(self._active_xlation_keys)
            if keys is not None:
                active &= {k.strip() for k in keys
                           if isinstance(k, str) and k.strip()}
            code = lang.strip().split("-")[0] if isinstance(lang, str) else ""
            if code == self.DECL_LANG:
                return len(active), len(active)
            # under the code, not the locale a caller may be holding:
            # dictionaries are keyed by language, and asking for "de-DE"
            # otherwise answered that German had nothing translated at all
            translated = self._lang_cache.get(code, {})
            # an empty entry is no translation either -- the upload never
            # writes one, but a hand-edited file can
            done = sum(1 for k in active
                       if isinstance(translated.get(k), str) and translated[k])
        return done, len(active)

    def translate(self, key, lang):
        """
        The `lang` rendering of a display string, falling back to the string
        itself when the language is unknown or the entry is still untranslated.
        Every key is a DECL_LANG string, so the fallback is always readable --
        never a word from a third language. The key is noted as active on the
        way, so a string only ever spoken at runtime still shows up in the
        translation templates.
        """
        if not (isinstance(key, str) and key.strip()):
            return key
        key = key.strip()
        self._note_xlation_key(key)
        if not (isinstance(lang, str) and lang.strip()):
            return key
        lang = lang.strip()
        translated = self._translation_of(lang, key)
        if not translated and "-" in lang:
            # dictionaries are keyed by language, callers may hold a locale
            translated = self._translation_of(lang.split("-")[0], key)
        return translated or key

    def handle_value_event(self, value, alt_target_paths):
        """
        Asynchronous event-sink for external system modules (spec 4.9.3):
        transfers a backend-captured string value to a frontend client that
        is long-polling on one of the given candidate absolute paths; a '*'
        inside a path matches exactly one path element (e.g. a list
        ordinal). Without a matching waiting request, the event is safely
        discarded as a no-op. Returns True if the value was handed over to a
        waiting client, otherwise False, so that the calling module can tell an
        editor-driven capture apart from an event nobody was waiting for. At
        most one waiting request is served per invocation.
        """
        if not (isinstance(value, str) and
                isinstance(alt_target_paths, (list, tuple))):
            return False
        with self._lock:
            for path, waiter in list(self._capture_waiters.items()):
                if any(self._path_matches(pattern, path)
                       for pattern in alt_target_paths
                       if isinstance(pattern, str)):
                    # A value already serving elsewhere in a 'distinct_values'
                    # group is refused here, at the moment of capture. Waiting
                    # for Save would mean holding a card against the reader,
                    # seeing it accepted, and only later being told it is
                    # already the restart card -- and for these parameters
                    # capture is the only way in, so this is the only moment
                    # anybody can be told.
                    if CvvNode.value_breaks_distinct_values(self, path, value):
                        waiter["error"] = "duplicate_value"
                        waiter["event"].set()
                        del self._capture_waiters[path]
                        self._logger.info(
                                f"Captured value for '{path}' refused: it is "
                                "already in use within the same group.")
                        return True
                    waiter["value"] = value
                    waiter["event"].set()
                    del self._capture_waiters[path]
                    return True
        return False

    @staticmethod
    def _path_matches(pattern, path):
        pattern_elems = pattern.split(".")
        path_elems = path.split(".")
        return (len(pattern_elems) == len(path_elems) and
                all(pe in ("*", e)
                    for pe, e in zip(pattern_elems, path_elems)))

    # ------------------------------------------------------------------
    # Internal API for the config-editor layer (REST, see section 4 of
    # the spec); not intended for client modules
    # ------------------------------------------------------------------
    def _may_access(self, path):
        """
        True if the current session may touch the param at `path`: admin
        sessions always may, others only if no protected subtree covers it.
        """
        with self._lock:
            if self._session_admin:
                return True
        try:
            protected = CvvNode.get_protected_paths(
                    self, path.split(".", 1)[0])
        except CvvError:
            return True     # unknown modules resolve to 404 elsewhere
        return not any(path == p or path.startswith(p + ".")
                       for p in protected)
    def _apply_module_update(self, module_id, config_value):
        """
        Imposes verified user input onto the module's subtree, persists it,
        and notifies the module through its registered callback. Returns the
        list of rejected paths.
        """
        rejected, value = CvvNode.update_module(self, module_id, config_value)
        callback = self._callback_registry.get(module_id)
        if callable(callback):
            callback(value)
        return rejected

    def _probe_host(self, host):
        """
        Checks whether `host` -- the value of a 'pingable' param -- resolves
        and answers a ping. Two very different mistakes hide behind a plain
        "not reachable": a name that does not resolve is a typo, while a name
        that resolves but stays silent is a device switched off, firewalled or
        on another subnet. They are therefore reported apart. Only the backend
        can answer this usefully: what matters is whether *the device* reaches
        the host, not whether the browser showing the editor does.
        """
        try:
            info = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
        except OSError:
            return {"outcome": "unresolvable"}
        # A dual-stack name resolves to both an A and an AAAA record, and the
        # one the resolver puts first is not necessarily the one the device can
        # route. Trying the alternative keeps a working host from being
        # reported as silent; two are enough, there is no third protocol.
        addresses = list(dict.fromkeys(i[4][0] for i in info))[:2]
        # ICMP itself would need a raw socket and hence root, which the app
        # must not require; the system's ping binary carries that privilege
        flags = (["-n", "1", "-w", str(self.PING_TIMEOUT * 1000)]
                     if os.name == "nt" else
                 ["-c", "1", "-W", str(self.PING_TIMEOUT)])
        for address in addresses:
            try:
                if subprocess.run(
                        ["ping"] + flags + [address],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        timeout=self.PING_TIMEOUT + 3).returncode == 0:
                    return {"outcome": "reachable", "address": address}
            except (OSError, subprocess.SubprocessError):
                break       # no usable ping binary; do not retry per address
        return {"outcome": "silent", "address": addresses[0]}

    def _probe_path(self, path):
        """
        Checks the value of a 'path' param against the device's own file
        system -- which, again, only the backend can see. Absence is not
        necessarily an error: a log file is written later, a folder may be
        created on first use. So a missing path whose parent folder exists is
        reported as creatable, and only a missing parent -- nearly always a
        typo -- as missing. A leading '~' is expanded, because it is the
        service account's home that the module will resolve it against.
        """
        path = os.path.expanduser(path)
        if os.path.isdir(path):
            return {"outcome": "directory"}
        if os.path.exists(path):
            return {"outcome": "file"}
        parent = os.path.dirname(os.path.abspath(path))
        return {"outcome": "creatable" if os.path.isdir(parent) else "missing"}

    def _stage_web_assets(self):
        """
        Copies the editor's web assets into ui_dir from the packaged defaults,
        so that a freshly provisioned appliance serves the editor out of the
        box. An asset that the deployment has edited is left alone, but one
        still identical to what an earlier version of this package staged is
        refreshed: otherwise upgrading the package would keep serving the old
        frontend, and a fix in it would silently never reach the device. The
        first run after that rule was introduced finds no record of what was
        staged; a differing asset is then set aside as '<name>.local' rather
        than lost.
        """
        packaged_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ui")
        stamp_file = os.path.join(self.ui_dir, self.ASSET_STAMP)
        try:
            with open(stamp_file, encoding="utf-8") as handle:
                staged = json.load(handle)
        except (OSError, ValueError):
            staged = {}
        if not isinstance(staged, dict):
            staged = {}

        def digest(path):
            with open(path, "rb") as handle:
                return hashlib.sha256(handle.read()).hexdigest()

        for asset in self.WEB_ASSETS:
            source = os.path.join(packaged_dir, asset)
            target = os.path.join(self.ui_dir, asset)
            if not os.path.exists(source):
                continue
            try:
                packaged = digest(source)
                if os.path.exists(target):
                    local = digest(target)
                    if local == packaged:
                        staged[asset] = packaged        # already up to date
                        continue
                    if asset in staged:
                        if local != staged[asset]:
                            self._logger.info(
                                    f"Keeping the locally modified '{asset}'; "
                                    "the packaged version has changed.")
                            continue
                    else:
                        shutil.copyfile(target, target + ".local")
                        self._logger.warning(
                                f"Replacing the unrecorded '{asset}' with the "
                                f"packaged one; the previous file is kept as "
                                f"'{asset}.local'.")
                shutil.copyfile(source, target)
                staged[asset] = packaged
            except OSError as exc:
                self._logger.error(f"Staging '{asset}' failed: {exc}")
        try:
            with open(stamp_file, "w", encoding="utf-8") as handle:
                json.dump(staged, handle)
        except OSError as exc:
            self._logger.error(f"Recording the staged assets failed: {exc}")

    def _resolve_backend_func(self, module_id, func_name):
        """
        Resolves a function name referenced within a Declaration (e.g. the
        dynamic 'values' provider of an enum, see section 4.9.1 of the spec)
        within the func_dict provided by the registering client module.
        """
        return self._func_registry.get(module_id, {}).get(func_name)

    # ------------------------------------------------------------------
    # Multi-linguality (spec 4.3 and 4.3.1)
    # ------------------------------------------------------------------
    def _init_lang_support(self):
        self._active_xlation_keys = set(self.OWN_UI_KEYS)
        # what each display string is, so that a translator can see it: the
        # same words are handled differently depending on where they appear
        self._xlation_kinds = {key: {"ui"} for key in self.OWN_UI_KEYS}
        self._lang_cache = {}
        self._lang_dir = os.path.join(self.ui_dir, "lang")
        os.makedirs(self._lang_dir, exist_ok=True)
        self._language_validator = None
        self._language_options = self._load_language_options()

        # Seed the translation dictionaries shipped with the release into
        # ui_dir/lang/ -- but only into an empty directory. A deployment that
        # does not want the packaged translations may set
        # GPSMCPMMS_NO_LANG_SEED=1 to skip this entirely.
        #
        # All or nothing, and not file by file: a deployment that has its own
        # dictionaries has decided which languages it speaks. Seeding the
        # missing ones into it would add whichever languages the package
        # happens to ship -- covering this library's own strings and nothing
        # of the host's, so the new language would appear as supported, be
        # offered to users, and read half in a language they did not ask for.
        # Which is what happened the moment a release shipped one more
        # dictionary than the devices in the field had.
        packaged_lang = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ui", "lang")
        if (os.path.isdir(packaged_lang) and
                not os.environ.get("GPSMCPMMS_NO_LANG_SEED") and
                not any(f.endswith(".json")
                        for f in os.listdir(self._lang_dir))):
            for file_name in os.listdir(packaged_lang):
                if not file_name.endswith(".json"):
                    continue
                try:
                    shutil.copyfile(os.path.join(packaged_lang, file_name),
                                    os.path.join(self._lang_dir, file_name))
                except OSError as exc:
                    self._logger.error(f"Seeding '{file_name}' failed: {exc}")

        for file_name in sorted(os.listdir(self._lang_dir)):
            if not file_name.endswith(".json"):
                continue
            lang_code = os.path.splitext(file_name)[0]
            file_path = os.path.join(self._lang_dir, file_name)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lang_dict = json.load(f)
                if not isinstance(lang_dict, dict):
                    raise ValueError("content is not a json object")
            except (OSError, ValueError) as exc:
                # spec 4.3.1: quarantine the broken file and regenerate a
                # fresh default dictionary instead of crashing
                self._logger.critical(
                    f"Quarantining broken translation dictionary "
                    f"'{file_name}': {exc}")
                try:
                    os.replace(file_path, file_path + ".broken")
                except OSError:
                    pass
                lang_dict = {}
            self._lang_cache[lang_code] = lang_dict

        if self.DECL_LANG not in self._lang_cache:
            self._lang_cache[self.DECL_LANG] = {}

        # A dictionary that covers not a single one of this library's own
        # display strings was written against different keys -- almost always
        # one from before the source language changed. Nothing is broken: the
        # editor falls back to the keys and stays readable. But it reads in
        # DECL_LANG, and every language reports incomplete, and neither is
        # obvious from looking at it. Said once at startup, it costs a line;
        # unsaid, it costs somebody an afternoon.
        own = set(self.OWN_UI_KEYS)
        for lang, entries in sorted(self._lang_cache.items()):
            if lang == self.DECL_LANG or not entries or not own:
                continue
            if not (own & set(entries)):
                self._logger.warning(
                        f"Translation dictionary '{lang}' has {len(entries)} "
                        f"entries but none for the {len(own)} display strings "
                        f"of this library. It was written against different "
                        f"keys -- if the source language changed, replace the "
                        f"dictionaries in '{self._lang_dir}' with the ones "
                        f"shipped in the package.")

        for lang, lang_dict in self._lang_cache.items():
            lang_dict["lang_cache_modified"] = False
            self._migrate_lang_format(lang, lang_dict)

    def _migrate_lang_format(self, lang, lang_dict):
        """Brings a dictionary from the old encoding to the current one, once.

        Until format 2 every known key was written into every dictionary as its
        own value, and *that* was how "not translated yet" was recorded. Now an
        absent entry says it, and an entry reading like the German says the
        opposite: somebody looked at this string and decided it stays. Both
        cannot be true of the same file, so the old entries have to go -- once,
        and marked, because after the migration those very entries are the
        deliberate ones and must survive every later start.

        What this costs is the handful of words that were already right by
        coincidence -- "OK" is Polish for OK -- and they have to be entered
        again. There is no way to tell them apart from the thousands that were
        merely never touched; only the person translating knows.
        """
        if lang_dict.get(self.LANG_FORMAT_KEY) == self.LANG_FORMAT:
            return
        stale = [k for k, v in lang_dict.items()
                 if k not in self.RESERVED_LANG_KEYS and v == k]
        for key in stale:
            del lang_dict[key]
        lang_dict[self.LANG_FORMAT_KEY] = self.LANG_FORMAT
        lang_dict["lang_cache_modified"] = True
        if stale:
            self._logger.info(
                    f"Translation dictionary '{lang}': {len(stale)} entries "
                    "that merely repeated the German key were dropped; they "
                    "used to mean 'untranslated'. An entry equal to the "
                    "German now means the opposite, and is kept.")

    def _harvest_xlation_keys(self, decl_data, funcs=None):
        """
        Collects all display strings -- labels, tooltips, placeholders,
        acquire-button labels, hints and test messages, including those of enum
        options -- from registered declaration data as keys into the
        translation dictionaries.

        `funcs` is the registering module's func_dict, needed to tell the two
        kinds of hint apart: a hint that names a provider is a function name,
        not a display string, and translating it would put "get_lang_report" in
        front of every translator.
        """
        if not isinstance(decl_data, dict):
            return
        for k, v in decl_data.items():
            if k in ("default_val", "fixed_val", "likely_val"):
                continue    # declared values are data, not display strings
            if (k in self.XLATION_DECL_KEYS and
                    isinstance(v, str) and v.strip()):
                if k == "hint" and funcs and v.strip() in funcs:
                    continue
                self._note_xlation_key(v.strip(), self.DECL_KEY_KINDS.get(k))
            elif isinstance(v, dict):
                self._harvest_xlation_keys(v, funcs)

    def _check_values_for(self, decl_data, funcs):
        """
        Verifies at registration that a 'values_for' provider can actually be
        called with an argument.

        Without this the mismatch surfaced as a 500 the first time somebody
        expanded the group -- a stack trace in the log, an unusable field on
        screen, and nothing naming the declaration that caused it. A wrong
        signature is a mistake in the source, so it belongs to startup, where
        the person who can fix it is still looking.
        """
        if not isinstance(decl_data, dict):
            return
        for key, value in decl_data.items():
            if not isinstance(value, dict):
                continue
            self._check_values_for(value, funcs)
            if "values_for" not in value:
                continue
            provider = value.get("values")
            func = funcs.get(provider) if isinstance(provider, str) else None
            if func is None:
                raise ValueError(
                        f"register_params(): '{key}' declares 'values_for' "
                        f"but its 'values' ({provider!r}) is not a function "
                        "in func_dict.")
            try:
                inspect.signature(func).bind(None)
            except TypeError:
                raise ValueError(
                        f"register_params(): the provider '{provider}' of "
                        f"'{key}' has to take the value of "
                        f"'{value['values_for']}' as its argument.") from None

    def _note_xlation_key(self, xlation_key, kind=None):
        # Nothing is written into the dictionaries here. A key they do not
        # carry is a key nobody has translated -- which is all the template
        # needs to know, and it leaves "the entry reads like the key" free to
        # mean what a translator would want it to mean.
        #
        # Every key is a DECL_LANG string; there is no language to record. A
        # module that receives its wording in another language settles on a
        # DECL_LANG one and hands the original over through
        # add_original_xlations() -- see there for why that is the only way in.
        with self._lock:
            late = (self._keys_at_start is not None and
                    xlation_key not in self._active_xlation_keys)
            self._active_xlation_keys.add(xlation_key)
            if kind:
                # a string can be several things at once: the name of a
                # service type is shown in a list *and* read aloud
                self._xlation_kinds.setdefault(xlation_key, set()).add(kind)
        if late:
            # A key that appears only once the editor is running was not in the
            # template anybody cut before that, and not in the count that told
            # them the languages were complete. Which is how a set of
            # translations goes out believing itself finished.
            #
            # Reported and not refused: a string that first exists when
            # something is rendered is legitimate, and a host cannot always
            # know it earlier. But whoever builds a release image should see in
            # the log that the key set is not the one they froze -- once per
            # key, and on a device that declares everything up front, never.
            self._logger.info(
                    f"Translation key {xlation_key!r} appeared after the editor "
                    f"started; it was in no template cut before now. Register "
                    f"it at startup (note_xlation_keys) if it is meant to be "
                    f"translated.")

    def _orphan_keys_of(self, lang_dict):
        # a key is orphaned when no active registration uses it (anymore)
        return sorted(k for k in lang_dict
                      if k not in self.RESERVED_LANG_KEYS and
                         k not in self._active_xlation_keys)

    def _write_translation_file(self, lang_code, lang_dict):
        file_path = os.path.join(self._lang_dir, f"{lang_code}.json")
        try:
            tmp_path = file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                # side-effect of saving "lang_cache_modified" is no problem
                json.dump(lang_dict, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, file_path)
            return True
        except OSError as exc:
            self._logger.error(f"Saving translation dictionary "
                               f"'{lang_code}' failed: {exc}")
            return False

    def _get_translation_dict(self, lang_code):
        with self._lock:
            if not lang_code or lang_code not in self._lang_cache:
                lang_code = self.DECL_LANG
            lang_dict = self._lang_cache[lang_code]
            file_path = os.path.join(self._lang_dir, f"{lang_code}.json")
            if (lang_dict.get("lang_cache_modified") or
                    not os.path.exists(file_path)):
                lang_dict["lang_cache_modified"] = False
                if not self._write_translation_file(lang_code, lang_dict):
                    lang_dict["lang_cache_modified"] = True
            return dict(lang_dict)

    def _store_translation_dict(self, lang, lang_dict, replace=None):
        """
        Realizes the admin actions on translation dictionaries specified in
        section 4.5 of the spec (add / clean up / align); returns an error
        tag or None.
        """
        if not (isinstance(lang, str) and re.fullmatch(r"[a-z]{2,3}", lang)):
            return "invalid_lang"
        # an empty dict is allowed: it just means "all entries fall back to
        # German" -- a language may legitimately be only partially translated
        if not (isinstance(lang_dict, dict) and all(
                    isinstance(k, str) and isinstance(v, str)
                    for k, v in lang_dict.items()
                    if k not in self.RESERVED_LANG_KEYS)):
            return "invalid_dict"
        if not self._language_allowed(lang):
            return "language_not_allowed"

        with self._lock:

            lang_dict = {k: v for k, v in lang_dict.items()
                         if k not in self.RESERVED_LANG_KEYS}
            lang_dict["lang_cache_modified"] = False

            # atomic write-and-update: cache first, then disk (spec 4.3.1)
            self._lang_cache[lang] = lang_dict
            if replace is not None:
                self._lang_cache.pop(replace, None)
                try:
                    os.remove(os.path.join(self._lang_dir,
                                           f"{replace}.json"))
                except OSError:
                    pass
            if not self._write_translation_file(lang, lang_dict):
                lang_dict["lang_cache_modified"] = True
        return None

    # ------------------------------------------------------------------
    # CSV round-trip for translations (spec 4.5): a template with the German
    # source and up to MAX_TEMPLATE_REFS reference columns is downloaded,
    # filled offline (a human or an AI assistant), and uploaded again; the
    # backend answers with the same rows plus a status column.
    # ------------------------------------------------------------------
    def _active_keys_sorted(self):
        with self._lock:
            return sorted(self._active_xlation_keys)

    def _translatable_keys_sorted(self):
        """Everything worth putting in front of a translator: what the
        software uses now, plus everything any dictionary already holds.

        The two are not the same, and the difference is not academic. A
        runtime string -- the name of an H4H service type -- enters the active
        set only once something has asked the server, so between a restart and
        the first such question the eight names are missing from it while
        their translations sit in every dictionary. A template cut in that
        window offered 190 rows instead of 198, and the eight best-reviewed
        lines in the file were the ones it left out.

        Keys that really have fallen out of the software are still listed for
        the admin (see /api/lang/info), where removing them is a decision.
        """
        with self._lock:
            keys = set(self._active_xlation_keys)
            for lang_dict in self._lang_cache.values():
                keys.update(k for k in lang_dict
                            if k not in self.RESERVED_LANG_KEYS)
        return sorted(keys)

    def _kinds_of(self, key):
        """What a display string is, for the template's second column.

        Sorted by XLATION_KINDS rather than alphabetically, so that the column
        reads the same way down the whole file and "label, speech" never
        appears once as "speech, label". Empty for a string whose host never
        said -- better an empty cell than a guess, since the guess a
        translator would act on is the one that costs an announcement.
        """
        with self._lock:
            kinds = set(self._xlation_kinds.get(key) or ())
        return ", ".join(k for k in self.XLATION_KINDS if k in kinds)

    def _translation_of(self, lang, key):
        """The stored translation of `key` in `lang`, or "" if there is none.

        An entry that reads like the German is one of them: somebody decided
        this string stays as it is -- because the word is the same in both
        languages, or because it is not really a word, like the placeholder
        showing the shape of a phone number.
        """
        with self._lock:
            v = self._lang_cache.get(lang, {}).get(key)
        return v if isinstance(v, str) else ""

    def _lang_template_csv(self, target, refs):
        """Builds the CSV template for translating into `target`: the source
        keys, what each of them is, which language it is written in, one column
        per reference language, and the target column (pre-filled with any
        existing translation).

        DECL_LANG always travels as a reference, even unasked. A key written in
        German gets its English beside it and vice versa, so neither language
        reads as the privileged one -- which is the truth of it: this library
        writes English keys, a host may write its own in something else, and the
        'src' column says which is which per row.
        """
        with self._lock:
            existing = set(self._lang_cache)
        # The protected languages lead, both of them, and neither is "the key
        # column": whichever of the two a row was written in, the other holds
        # its translation, so both cells are filled and a translator reads
        # whichever they know. There used to be a `key` column in front, which
        # meant every row had one empty cell among these two -- empty precisely
        # because that text was sitting in `key` instead.
        leading = [lang for lang in self.protected_langs()
                   if lang != target]
        seen = set(leading)
        extra = []
        for r in refs:
            if r in existing and r != target and r not in seen:
                seen.add(r)
                extra.append(r)
        extra = extra[:self.MAX_TEMPLATE_REFS]
        # There is no column saying which of the leading two is the original,
        # because knowing it would change nothing. A key *is* its text, so
        # rewording a source string produces a new key rather than staling an
        # old translation: what a translator meets is a filled cell or an empty
        # one, never a filled cell that has quietly gone wrong. Both languages
        # are therefore equally good to translate from, and the choice is the
        # translator's -- whichever they read.
        #
        # 'kind' is not a language, and the upload finds its columns by name and
        # ignores the others, so nothing has to be taught about it; a language
        # code is two or three letters, so the name cannot collide with one.
        columns = leading + ["kind"] + extra + [target]

        buf = io.StringIO()
        # QUOTE_ALL: every field is wrapped in double quotes (RFC 4180) so that
        # punctuation embedded in a key or translation -- notably a semicolon,
        # which German spreadsheets use as their own list separator -- can never
        # be mistaken for a column separator
        writer = csv.writer(buf, delimiter=self.CSV_DELIMITER,
                            quoting=csv.QUOTE_ALL)
        writer.writerow(columns)
        for key in self._translatable_keys_sorted():
            # in the column of the language it is written in, a key stands for
            # itself
            row = [key if lang == self.DECL_LANG
                   else self._translation_of(lang, key) for lang in leading]
            row += [self._kinds_of(key)]
            row += [self._translation_of(r, key) for r in extra]
            row.append(self._translation_of(target, key))
            writer.writerow(row)
        # UTF-8 BOM so that spreadsheet apps open the umlauts correctly
        return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8")

    @staticmethod
    def _parse_csv(raw):
        text = raw.decode("utf-8-sig", errors="replace")
        first_line = text.split("\n", 1)[0] if text else ""
        # prefer the pipe we write, but still tolerate whatever delimiter the
        # operator's spreadsheet may have produced (comma, semicolon, tab)
        delimiter = max((ConfigManager.CSV_DELIMITER, ",", ";", "\t"),
                        key=first_line.count)
        return list(csv.reader(io.StringIO(text), delimiter=delimiter))

    def _apply_lang_csv(self, target, raw, remove=None):
        """Applies an uploaded translation CSV to `target`. Returns
        (report_bytes, translated, total) on success, or (None, error, None)
        where error is a string tag or a dict for the removal prompt."""
        if not (isinstance(target, str) and re.fullmatch(r"[a-z]{2,3}", target)):
            return None, "invalid_lang", None
        if target == self.DECL_LANG:
            return None, "cannot_edit_de", None
        if raw[:4] == b"PK\x03\x04":
            # an .xlsx/.ods workbook (a ZIP), not a text CSV
            return None, "not_a_csv_file", None

        try:
            rows = self._parse_csv(raw)
        except Exception:
            return None, "unreadable_file", None
        if not rows:
            return None, "empty_file", None

        header = [c.strip() for c in rows[0]]
        if target not in header:
            return None, "target_column_missing", None
        tgt_idx = header.index(target)
        # Which cell of a row is the key it edits. Not a fixed column: a row is
        # written in DECL_LANG, so that is where its key stands. Tried rather
        # than assumed, and with the older header names as further candidates,
        # so a template downloaded before any of this still uploads.
        candidates = [header.index(lang) for lang in self.protected_langs()
                      if lang in header and header.index(lang) != tgt_idx]
        if self.KEY_COLUMN in header:
            candidates.insert(0, header.index(self.KEY_COLUMN))
        if not candidates:
            candidates = [0]
        if not self._language_allowed(target):
            return None, "language_not_allowed", None

        # The same set the template was cut from -- not merely what this run
        # has got round to registering. "Not active right now" is not the same
        # as "no longer used": the H4H service names enter the active set only
        # once somebody has asked the server, so an upload made before that
        # deleted all eight translations of them, silently, for a reason
        # nobody could see. Keys that really have fallen out of the software
        # are listed for the admin (see /api/lang/info), where removing them
        # is a decision rather than a side effect.
        known = set(self._translatable_keys_sorted())

        uploaded = {}
        for row in rows[1:]:
            if len(row) <= tgt_idx:
                continue
            cells = [row[idx].strip() for idx in candidates if idx < len(row)]
            # the first cell that is a key wins; failing that the first
            # non-empty one, which the report can then name as unknown
            key = next((c for c in cells if c in known),
                       next((c for c in cells if c), ""))
            if key:
                uploaded[key] = row[tgt_idx].strip()

        with self._lock:
            new_dict = {k: v for k, v in self._lang_cache.get(target, {}).items()
                        if k not in self.RESERVED_LANG_KEYS}
        # the uploaded rows edit only the keys they contain: a non-empty cell
        # sets a translation, a blank cell clears one; keys absent from the
        # file keep whatever translation they already had.
        # A cell repeating the German is a translation like any other, and the
        # only way to say "this one stays as it is" -- refusing it left every
        # such string looking untranslated for ever.
        for key, value in uploaded.items():
            if key not in known:
                continue
            if value:
                new_dict[key] = value
            else:
                new_dict.pop(key, None)

        failure = self._store_translation_dict(target, new_dict)
        if failure:
            return None, failure, None
        report = self._lang_report_csv(target, known, uploaded, new_dict)
        translated = sum(1 for k in known if k in new_dict)
        return report, translated, len(known)

    def _lang_report_csv(self, target, active, uploaded, new_dict):
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.CSV_DELIMITER,
                            quoting=csv.QUOTE_ALL)
        writer.writerow([self.KEY_COLUMN, target, "status"])
        for key in sorted(active):
            value = new_dict.get(key, "")
            if key in uploaded:
                status = "applied" if value else "no translation"
            elif value:
                status = "unchanged"
            else:
                status = "not in file"
            writer.writerow([key, value, status])
        for key, value in uploaded.items():
            if key not in active:
                writer.writerow([key, value, "skipped: unknown key"])
        return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8")

    @staticmethod
    def _env_int(name, fallback, minimum=None, maximum=None):
        """
        Return int(os.environ[name]) when that variable is set to a valid
        integer within [minimum, maximum]; otherwise the given fallback. Keeps
        a mistyped or out-of-range deploy-time variable from crashing the
        import-time creation of the singleton.
        """
        raw = os.environ.get(name)
        if raw is None:
            return fallback
        try:
            value = int(raw)
        except ValueError:
            return fallback
        if (minimum is not None and value < minimum) or \
           (maximum is not None and value > maximum):
            return fallback
        return value

    # ------------------------------------------------------------------
    # Exclusive editing session of the config-editor (spec 4.8)
    # ------------------------------------------------------------------
    def _current_ui_passwd(self):
        key = f"{self.OWN_MODULE_ID}.ui_passwd"
        v = self.query(key).get(key)
        return v if isinstance(v, str) and v else self.FACTORY_DEFAULT_PASSWD

    def _session_timeout_seconds(self):
        return (self._session_timeout or self.DEFAULT_SESSION_TIMEOUT) * 60

    def _session_status(self, token):
        """
        'valid': the provided token is the active one; 'none': no active
        session exists; 'other': another session holds the exclusive token.
        """
        with self._lock:
            if (self._session_token is None or
                    time.time() > self._session_expires):
                if self._session_token is not None:
                    self._logger.info(
                            f"Editing session of "
                            f"{self._session_owner or 'unknown'} expired after "
                            "its idle timeout; the editor is writable again.")
                self._session_token = None
                self._session_admin = False
                self._session_owner = None
                return "none"
            return ("valid"
                        if isinstance(token, str) and hmac.compare_digest(
                                token, self._session_token) else
                    "other")

    def _issue_session_token(self, owner=None):
        timeout = self._session_timeout_seconds()
        with self._lock:
            self._session_token = secrets.token_urlsafe(32)
            self._session_admin = False
            self._session_owner = owner
            self._session_expires = time.time() + timeout
            return self._session_token

    def _report_session_conflict(self, applicant):
        """
        Says in the log why an editor came up read-only. Without this the
        banner on the screen is the only evidence, and it cannot say who is
        holding the session or for how much longer -- which is exactly what
        somebody locked out of their own device needs to know.
        """
        with self._lock:
            owner = self._session_owner or "unknown"
            left = max(0, int(self._session_expires - time.time()))
        self._logger.warning(
                f"Read-only editor for {applicant or 'unknown'}: the session "
                f"of {owner} holds the write lock for another "
                f"{left // 60} min {left % 60} s. It is released by 'end "
                f"session', by that idle timeout, or by restarting the app.")

    def _lock_free_in(self):
        """Seconds until the foreign session lapses on its own.

        A lower bound, not a promise: every request from the holder restarts
        the timer (_touch_session). Someone who simply closed the editor never
        touches it again -- and that is the case this answer is meant for.
        """
        with self._lock:
            if self._session_token is None:
                return None
            return max(0, int(self._session_expires - time.time()))

    def _touch_session(self):
        # each valid request restarts the inactivity timer (spec 4.8)
        timeout = self._session_timeout_seconds()
        with self._lock:
            self._session_expires = time.time() + timeout

    def _invalidate_session(self, reason):
        """
        Drops the exclusive editing session. `reason` reaches the log, so that
        an admin whose session vanished mid-edit can see what took it. Nothing
        is logged when there was no session: at startup every module
        registration lands here, and an ending that never began is noise.
        """
        with self._lock:
            existed = self._session_token is not None
            owner = self._session_owner
            self._session_token = None
            self._session_admin = False
            self._session_owner = None
        if existed:
            self._logger.info(f"Editing session of {owner or 'unknown'} ended "
                              f"({reason}); the editor is writable again.")

    # ------------------------------------------------------------------
    # Handling of protected params (spec 4.4)
    # ------------------------------------------------------------------
    @staticmethod
    def _strip_protected_nodes(node):
        """
        Removes protected subtrees from one parsed dump node;
        returns (node or None, True if anything was stripped).
        """
        if node.get("protected"):
            return None, True
        stripped = False
        children = node.get("children")
        if isinstance(children, dict):
            kept = {}
            for k, c in children.items():
                kc, ks = ConfigManager._strip_protected_nodes(c)
                stripped = stripped or ks
                if kc is not None:
                    kept[k] = kc
            node["children"] = kept
        template = node.get("item_template")
        if isinstance(template, dict):
            kt, ks = ConfigManager._strip_protected_nodes(template)
            stripped = stripped or ks
            if kt is None:
                node.pop("item_template", None)
            else:
                node["item_template"] = kt
        return node, stripped

    def _strip_protected_updates(self, module_id, value, rejected):
        """
        Removes all entries addressing protected params from an update
        payload of a non-admin session, noting them as rejected.
        """
        for path in CvvNode.get_protected_paths(self, module_id):
            rel = path.split(".")[1:]
            if not rel:
                continue
            dotted = ".".join(rel)
            if dotted in value:
                del value[dotted]
                rejected.append(path)
                continue
            d = value
            for seg in rel[:-1]:
                d = d.get(seg) if isinstance(d, dict) else None
                if d is None:
                    break
            if isinstance(d, dict) and rel[-1] in d:
                del d[rel[-1]]
                rejected.append(path)

    # ------------------------------------------------------------------
    # The flask-based config-editor backend (spec 4.2, 4.4, 4.7, 4.8)
    # ------------------------------------------------------------------
    def start_editor(self, run_server=True):
        """
        Creates the flask app serving the config-editor and its REST-API;
        unless run_server is False (tests), the app is served in a daemon
        thread on the port taken from GPSMCPMMS_UI_PORT. That port is a
        deploy-time decision, not a configurable parameter: whoever changed
        it from the editor would be sawing off the branch they sit on.
        """
        from flask import (Flask, Response, abort, jsonify, request,
                           send_from_directory)
        from urllib.parse import urlsplit

        with self._lock:
            if self._editor_started:
                return
            self._editor_started = True
            # Everything the software has declared of itself by now. What turns
            # up after this point is reported, once per key -- see
            # _note_xlation_key().
            self._keys_at_start = set(self._active_xlation_keys)

        self._stage_web_assets()

        app = Flask("gpsmcpmms_editor", static_folder=None)
        # Flask sorts the keys of every JSON response by default, which
        # alphabetised the children of each dump node on their way to the
        # editor -- so the screen showed parameters in an order nobody had
        # chosen. Declaration order survives everything else (Python dicts
        # keep insertion order, and so do JSON objects and JS objects with
        # non-numeric keys), so switching this off hands the ordering back to
        # whoever writes the param_dict, where it belongs. Module groups are
        # unaffected: the editor sorts those by id on purpose.
        app.json.sort_keys = False

        def request_token():
            token = request.headers.get(self.TOKEN_HEADER)
            if not token:
                token = request.args.get("token")
            if not token and request.method == "POST":
                payload = request.get_json(silent=True)
                if isinstance(payload, dict):
                    token = payload.get("token")
                elif request.form:      # multipart (e.g. CSV upload)
                    token = request.form.get("token")
            return token

        @app.before_request
        def reject_foreign_origins():
            # LAN-local anti-CSRF: only the app served by this host may
            # talk to the API (spec section 4, C)
            origin = request.headers.get("Origin")
            if origin and urlsplit(origin).netloc != request.host:
                abort(403)

        @app.route("/")
        def index():
            return send_from_directory(self.ui_dir, "index.html")

        @app.route("/style.css")
        def style_css():
            return send_from_directory(self.ui_dir, "style.css")

        @app.route("/app.js")
        def app_js():
            return send_from_directory(self.ui_dir, "app.js")

        @app.route("/api/cvv_data")
        def cvv_data():
            token = request_token()
            applicant = request.remote_addr
            status = self._session_status(token)
            if status == "none":
                # first client without an active session gets the token
                token = self._issue_session_token(applicant)
                status = "valid"
                self._logger.info(f"Editing session opened for {applicant}.")
            editable = status == "valid"
            if editable:
                self._touch_session()
            else:
                self._report_session_conflict(applicant)

            wrong_passwd = False
            passwd = request.args.get("passwd")
            if passwd is not None and editable:
                if hmac.compare_digest(passwd, self._current_ui_passwd()):
                    with self._lock:
                        self._session_admin = True
                else:
                    wrong_passwd = True
            with self._lock:
                admin = editable and self._session_admin

            cvv = json.loads(CvvNode.get_cvv_json_dump(self))
            # config_mgr's own module is handled internally, not in the editor
            cvv.pop(self.OWN_MODULE_ID, None)
            omitted = False
            if not admin:
                kept = {}
                for m_id, m_dump in cvv.items():
                    m_dump, stripped = self._strip_protected_nodes(m_dump)
                    omitted = omitted or stripped
                    if m_dump is not None:
                        kept[m_id] = m_dump
                cvv = kept

            return jsonify({
                "token": token if editable else None,
                "read_only": not editable,
                # how much longer the foreign session holds its lock -- as a
                # duration, not a wall-clock time. The browser turns it into a
                # time, because the browser's clock is the one to trust: a
                # device of this kind may have no RTC and start on whatever
                # fake-hwclock laid down, so a time computed here would be
                # wrong until the clock has been synchronised.
                "lock_free_in": None if editable else self._lock_free_in(),
                "admin": admin,
                "wrong_passwd": wrong_passwd,
                "protected_omitted": omitted,
                "factory_default_passwd":
                    self._current_ui_passwd() == self.FACTORY_DEFAULT_PASSWD,
                "cvv": cvv,
            })

        @app.route("/api/config/update", methods=["POST"])
        def config_update():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                abort(400)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()

            module = payload.get("module")
            value = payload.get("value")
            if not (isinstance(module, str) and module and
                    isinstance(value, dict)):
                abort(400)

            try:
                value = CvvNode.normalize_json_value(self, module, value)
            except CvvError as exc:
                return jsonify({"error": str(exc)}), 400

            rejected = []
            with self._lock:
                admin = self._session_admin
            if not admin:
                self._strip_protected_updates(module, value, rejected)
            try:
                rejected += self._apply_module_update(module, value)
            except CvvError as exc:
                self._logger.error(f"Update of '{module}' failed: {exc}")
                return jsonify({"error": str(exc)}), 500
            return jsonify({"rejected": rejected})

        @app.route("/api/schema")
        @app.route("/api/schema/<lang_code>")
        def schema(lang_code=None):
            return jsonify(self._get_translation_dict(lang_code))

        @app.route("/api/config/enum-options")
        def enum_options():
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = (request.args.get("path") or "").strip()
            if not path:
                abort(400)
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403
            constraints = CvvNode.get_node_constraints(self, path)
            if constraints is None:
                return jsonify({"error": "no_such_param"}), 404
            provider = constraints.get("one_of")
            if not isinstance(provider, str):
                return jsonify({"error": "not_a_dynamic_enum"}), 400
            func = self._resolve_backend_func(path.split(".", 1)[0],
                                              provider)
            if func is None:
                return jsonify({"error": f"unknown provider '{provider}'"})
            # 'values_for': the options are computed for the current value of
            # a sibling, which the editor sends along -- the one being edited,
            # not the one last saved. None while that sibling is unset.
            args = ()
            if constraints.get("one_of_for"):
                raw = request.args.get("arg")
                try:
                    args = (json.loads(raw) if raw else None,)
                except ValueError:
                    return jsonify({"error": "malformed argument"}), 400
            try:
                result = func(*args)
            except Exception as exc:
                self._logger.error(f"enum provider '{provider}' raised: "
                                   f"{exc}")
                result = "Internal error while determining the values"
            if isinstance(result, dict):
                # dynamically delivered labels/tooltips are display strings
                # and hence translation keys, too -- unless the provider says
                # otherwise. "de-DE-Wavenet-H" is a name the service made up,
                # and a device that offered fifty of them once put fifty rows
                # in front of every translator, for good: harvested keys stay
                # active as long as the provider still offers them.
                for option in result.values():
                    if not isinstance(option, dict):
                        continue
                    if option.get("verbatim"):
                        # the label is an identifier; a tooltip beside it is
                        # still prose and still wants translating
                        self._harvest_xlation_keys(
                                {"tooltip": option.get("tooltip")})
                    else:
                        self._harvest_xlation_keys(option)
                return jsonify({"values": result})
            return jsonify({"error": str(result)})

        @app.route("/api/value/capture")
        def value_capture():
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = (request.args.get("path") or "").strip()
            if not path:
                abort(400)
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403
            if CvvNode.get_node_constraints(self, path) is None:
                return jsonify({"error": "no_such_param"}), 404

            event = threading.Event()
            waiter = {"event": event, "value": None, "error": None}
            with self._lock:
                # a newer capture request replaces an older one on the same
                # path; the replaced request simply runs into its timeout
                self._capture_waiters[path] = waiter
            if event.wait(self.CAPTURE_TIMEOUT):
                if waiter["error"]:
                    # the German key itself: the editor runs it through its
                    # own translation, which is where the session's language
                    # is known
                    return jsonify({"error": "Wert bereits vergeben"}), 409
                return jsonify({"value": waiter["value"]})
            with self._lock:
                if self._capture_waiters.get(path) is waiter:
                    del self._capture_waiters[path]
            return jsonify({"value": None, "timeout": True})

        @app.route("/api/config/hint")
        def config_hint():
            """The current text of a provider-backed hint, with the moment it
            was established (spec 4.9.5).

            The moment is the point of the whole endpoint. A hint asserts
            something about the present -- "all seven languages are settled" --
            and an assertion nobody dated goes on claiming it long after it
            stopped being so. Stamped, it stays true.
            """
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = (request.args.get("path") or "").strip()
            lang = ((request.args.get("lang") or "").strip()
                    or self.DECL_LANG)
            if not path:
                abort(400)
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403
            provider = CvvNode.get_hint(self, path)
            if not isinstance(provider, str):
                return jsonify({"error": "no_such_hint"}), 404
            func = self._resolve_backend_func(path.split(".", 1)[0], provider)
            if func is None:
                # a literal hint travels in the schema and is never fetched;
                # asking for one here is a mistake worth reporting as such
                return jsonify({"error": "not_a_dynamic_hint"}), 404
            try:
                text = func(lang)
            except Exception as exc:
                self._logger.error(f"hint provider '{provider}' raised: {exc}")
                return jsonify(
                        {"error": "Internal error while establishing the hint"})
            return jsonify({"text": str(text), "at": time.strftime("%H:%M")})

        @app.route("/api/config/file", methods=["POST"])
        def config_file():
            """Takes an uploaded file for a parameter of type 'file': stores
            it in the directory the host declared and sets the parameter to
            its name (spec 2.1, type 'file')."""
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = (request.form.get("path") or "").strip()
            upload = request.files.get("file")
            if not path or upload is None:
                abort(400)
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403

            constraints = CvvNode.get_node_constraints(self, path) or {}
            file_dir = CvvNode.get_file_dir(self, path)
            if constraints.get("type") != "file" or not file_dir:
                return jsonify({"error": "not_a_file_param"}), 400

            # The browser decides what to call it, so nothing it says is
            # trusted. Note this refuses rather than cleans: stripping a
            # directory off and carrying on would work, but a name that
            # arrives carrying "../.." is a signal and not a typo, and the
            # cleaned version hides it. Comparing against basename() also
            # catches a forward slash on Windows, where the explicit test
            # below would not.
            raw = (upload.filename or "").strip()
            name = os.path.basename(raw)
            if (not name or name != raw or name in (".", "..") or
                    ".." in name or set(name) & {"/", "\\"} or
                    min(name) <= ' '):
                return jsonify({"error": "File name not allowed"}), 400

            pattern = constraints.get("patterned_string")
            if pattern and not re.fullmatch(pattern, name):
                return jsonify({"error": "File type not allowed"}), 400

            payload = upload.read(self.MAX_UPLOAD_BYTES + 1)
            if len(payload) > self.MAX_UPLOAD_BYTES:
                return jsonify({"error": "File too large"}), 400

            module, _, rest = path.partition(".")
            if not rest:
                abort(400)
            target = os.path.join(file_dir, name)
            existed = os.path.exists(target)
            try:
                os.makedirs(file_dir, exist_ok=True)
                with open(target, "wb") as f:
                    f.write(payload)
            except OSError as exc:
                self._logger.error(f"Storing '{target}' failed: {exc}")
                return jsonify({"error": "Invalid file"}), 500

            update = name
            for part in reversed([p for p in rest.split(".") if p]):
                update = {part: update}
            try:
                update = CvvNode.normalize_json_value(self, module, update)
                rejected = self._apply_module_update(module, update)
            except CvvError as exc:
                rejected = [str(exc)]
            if rejected:
                # the value did not take, so the file has no business being
                # there -- unless it was already there before we arrived
                if not existed:
                    try:
                        os.remove(target)
                    except OSError:
                        pass
                return jsonify({"error": "Abgelehnt", "rejected": rejected}), 400
            self._logger.info(f"'{path}' now points at the uploaded "
                              f"'{name}' in {file_dir}.")
            return jsonify({"value": name})

        @app.route("/api/config/test", methods=["POST"])
        def config_test():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                abort(400)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = payload.get("path")
            if not (isinstance(path, str) and path.strip()):
                abort(400)
            path = path.strip()
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403
            test_func = CvvNode.get_test_func(self, path)
            if test_func is None:
                return jsonify({"error": "no_test_func"}), 404
            try:
                result = test_func(payload.get("value"))
            except Exception as exc:
                self._logger.error(f"test_func for '{path}' raised: {exc}")
                return jsonify({"error": "test_failed"}), 500
            if not isinstance(result, (bool, int, float, str, type(None))):
                result = str(result)
            return jsonify({"result": result})

        @app.route("/api/config/probe", methods=["POST"])
        def config_probe():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                abort(400)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            path = payload.get("path")
            value = payload.get("value")
            if not (isinstance(path, str) and path.strip()
                    and isinstance(value, str) and value.strip()):
                abort(400)
            path = path.strip()
            if not self._may_access(path):
                return jsonify({"error": "admin_required"}), 403
            constraints = CvvNode.get_node_constraints(self, path)
            kind = constraints.get("type") if constraints else None
            # only what the declaration calls a host or a file may be probed:
            # this checks 'pingable' and 'path' params, it is neither a
            # general-purpose network prober nor a file browser
            if kind not in ("path", "pingable"):
                return jsonify({"error": "no_such_param"}), 404
            probe = self._probe_host if kind == "pingable" else self._probe_path
            return jsonify(probe(value.strip()))

        @app.route("/api/lang/info")
        def lang_info():
            editable = self._session_status(request_token()) == "valid"
            if editable:
                self._touch_session()
            with self._lock:
                # The source language belongs in the answer, not in the
                # editor's assumptions. It was hard-coded there once, and when
                # DECL_LANG moved the editor kept offering the source as a
                # translation target while hiding a language that needed one.
                options = self.language_options()
                # `bounded` says which of the two shapes the panel takes.
                # With a list, the picker is the only way in and the two
                # free-text fields are shut; without one, there is nothing to
                # pick from and typing is the way. The names travel either
                # way -- a dropdown of codes helps nobody.
                info = {"languages": sorted(self._lang_cache),
                        "source": self.DECL_LANG,
                        "bounded": options is not None,
                        "options": options if options is not None
                                   else dict(self.LANGUAGE_OPTIONS)}
                if editable and self._session_admin:
                    info["orphans"] = {
                        lang: self._orphan_keys_of(lang_dict)
                        for lang, lang_dict in self._lang_cache.items()
                    }
            return jsonify(info)

        @app.route("/api/lang/update", methods=["POST"])
        def lang_update():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                abort(400)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            with self._lock:
                admin = self._session_admin
            if not admin:
                return jsonify({"error": "admin_required"}), 403
            failure = self._store_translation_dict(
                    payload.get("lang"), payload.get("dict"),
                    payload.get("replace"))
            if failure:
                return jsonify({"error": failure}), 400
            return jsonify({"stored": payload.get("lang")})

        def _csv_download(data, filename):
            # Flask appends "; charset=utf-8" to a text/* mimetype itself
            return Response(data, mimetype="text/csv",
                            headers={"Content-Disposition":
                                     f'attachment; filename="{filename}"'})

        @app.route("/api/lang/template")
        def lang_template():
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            with self._lock:
                admin = self._session_admin
            if not admin:
                return jsonify({"error": "admin_required"}), 403
            target = (request.args.get("lang") or "").strip().lower()
            if (not re.fullmatch(r"[a-z]{2,3}", target)
                    or target == self.DECL_LANG):
                return jsonify({"error": "invalid_lang"}), 400
            refs = [r.strip().lower()
                    for r in (request.args.get("refs") or "").split(",")
                    if r.strip()]
            return _csv_download(self._lang_template_csv(target, refs),
                                 f"{target}.csv")

        @app.route("/api/lang/upload", methods=["POST"])
        def lang_upload():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            if self._session_status(request_token()) != "valid":
                return jsonify({"error": "invalid_token"}), 401
            self._touch_session()
            with self._lock:
                admin = self._session_admin
            if not admin:
                return jsonify({"error": "admin_required"}), 403
            upload = request.files.get("file")
            target = (request.form.get("lang") or "").strip().lower()
            remove = (request.form.get("remove") or "").strip().lower() or None
            name = (request.form.get("name") or "").strip()
            if upload is None or not target:
                abort(400)
            report, result, total = self._apply_lang_csv(
                    target, upload.read(), remove)
            if report is None:
                if isinstance(result, dict):
                    return jsonify(result), 409     # removal choice required
                return jsonify({"error": result}), 400
            # Recorded after the rows are applied, and only if they were. The
            # name now lives inside the dictionary it names, so there is
            # nothing to write it into until that dictionary exists -- this
            # ran first while the name went to languages.json, and moving it
            # is what keeps a new language from arriving nameless.
            if name:
                self.set_language_name(target, name)
            resp = _csv_download(report, f"{target}.report.csv")
            resp.headers["X-GPSMCPMMS-Translated"] = str(result)
            resp.headers["X-GPSMCPMMS-Total"] = str(total)
            return resp

        @app.route("/api/session/takeover", methods=["POST"])
        def session_takeover():
            """
            Wrests the exclusive editing session from whoever holds it, on
            proof of the admin password (spec 4.8).

            Without this an editor closed without ending its session locks the
            device for the rest of the idle timeout, and the admin standing in
            front of it has no way in -- reloading only discards their own
            token. The password is the same one that reveals protected
            parameters, and the new session starts in admin mode: see below for
            why asking for it a second time answers nothing.
            """
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            payload = request.get_json(silent=True)
            if not isinstance(payload, dict):
                abort(400)
            applicant = request.remote_addr
            if not hmac.compare_digest(str(payload.get("passwd") or ""),
                                       self._current_ui_passwd()):
                self._logger.warning(
                        f"Refused a session takeover from {applicant}: wrong "
                        "password.")
                return jsonify({"error": "wrong_passwd"}), 403
            with self._lock:
                previous = self._session_owner
            self._invalidate_session(f"taken over by {applicant}")
            token = self._issue_session_token(applicant)
            # The new session starts in admin mode. Only an admin can take a
            # session over at all -- the password was just checked -- so
            # handing back a read-only editor that immediately demands the
            # same password again asks the same question twice and answers
            # neither.
            with self._lock:
                self._session_admin = True
            self._logger.warning(
                    f"{applicant} took the editing session over from "
                    f"{previous or 'unknown'} and is in admin mode.")
            return jsonify({"token": token})

        @app.route("/api/end_session", methods=["POST"])
        def end_session():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            if self._session_status(request_token()) != "valid":
                return jsonify({"ended": False}), 401
            self._invalidate_session("closed by the editor")
            return jsonify({"ended": True})

        self._flask_app = app
        if run_server:
            threading.Thread(
                target=lambda: app.run(host="0.0.0.0", port=self._ui_port,
                                       threaded=True, use_reloader=False),
                daemon=True
            ).start()
            self._logger.info(f"Config-editor serving on port "
                              f"{self._ui_port}.")


# ---------------------------------------------------------------------------
# Module-level singleton — imported by all client modules
# ---------------------------------------------------------------------------
config_mgr = ConfigManager()
