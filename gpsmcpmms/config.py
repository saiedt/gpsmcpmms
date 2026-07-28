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
import hmac
import io
import json
import logging
import os
import re
import secrets
import shutil
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
    # translation dictionaries: at most this many languages in parallel; a
    # further one requires the admin to pick an existing language to remove
    MAX_LANGUAGES = 7
    # how many existing languages may be included as reference columns in a
    # downloaded translation template (context for the translator/AI)
    MAX_TEMPLATE_REFS = 3
    # column separator of the translation CSVs: a pipe is chosen because it is
    # very unlikely to occur inside a German key or a translation, so cells
    # never need quoting and no delimiter collision can arise
    CSV_DELIMITER = "|"

    # German display strings internal to config.py and its editor; they act
    # as keys into the translation dictionaries (spec 4.3)
    OWN_UI_KEYS = (
        "Hub4Help Konfigurationseditor",
        "Speichern", "Anwenden", "Entfernen", "Rückgängig",
        "Sitzung beenden", "Geschützte Parameter anzeigen",
        "Admin-Modus verlassen", "Sprache",
        "Falsches Passwort",
        "Nur-Lese-Modus: Eine andere Sitzung ist aktiv",
        "Das Gerät verwendet noch das werksseitige Standardpasswort",
        "Ungültige Eingabe", "Übernehmen fehlgeschlagen",
        "Verbindung zum Gerät verloren",
        "OK", "Abbrechen", "Gespeichert", "Abgelehnt", "Test", "Neu",
        "Passwort", "Neues Passwort",
        "Wert wird gelesen...", "Wert übernommen", "Zeitüberschreitung",
        "Eintrag wirklich entfernen?", "Liste ist voll",
        "Zu wenige Einträge in", "Erneut laden",
        "Erfolgreich", "Fehlgeschlagen",
        "Übersetzungen verwalten", "Zielsprache", "Neuer Sprachcode",
        "Referenzsprachen (max. 3)", "Vorlage herunterladen",
        "Übersetzungsdatei hochladen", "Hochladen",
        "Zu entfernende Sprache wählen", "übersetzt",
        "Übersetzung verarbeitet", "Ungültige Datei",
    )

    # Declaration keys whose string values are German display strings and
    # hence translation keys
    XLATION_DECL_KEYS = (
        "acquire_button", "label", "placeholder", "test_func_msg", "tooltip"
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

        # exclusive editing session of the config-editor (spec 4.8)
        self._session_token = None
        self._session_expires = 0.0
        self._session_admin = False
        self._editor_started = False
        self._flask_app = None

        # long-polling requests waiting for backend-captured values,
        # keyed by the absolute path of the target param (spec 4.9.3)
        self._capture_waiters = {}

        # initialize cvv and own config params
        self._cvv_root = CvvNode.register(self, self.cvv_dir)
        CvvNode.set_logger(self, self._logger)
        own_decl = { "type": self.OWN_MODULE_ID, "label": "Konfigurationsdienst" }
        own_types = { self.OWN_MODULE_ID: {
                "ui_passwd": {
                    "type": "password", "label": "UI-Passwort",
                    "protected": True,
                    "default_val": self.FACTORY_DEFAULT_PASSWD,
                    "tooltip": "Administrator-Passwort zum Freischalten "
                             + "geschützter Parameter."
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
            self._note_xlation_key(module_label.strip())
        if isinstance(module_tooltip, str) and module_tooltip.strip():
            self._note_xlation_key(module_tooltip.strip())
        self._harvest_xlation_keys(param_dict)
        self._harvest_xlation_keys(type_dict)
        type_registry = type_dict if isinstance(type_dict, dict) else {}
        type_registry[module_id] = param_dict
        config_value = CvvNode.init_module(self, module_id, {
                "label": module_label,
                "tooltip": module_tooltip,
                "type": module_id
            }, type_registry)
        # any runtime schema change invalidates the exclusive editing
        # token, forcing the config-editor to re-align (spec 4.8)
        self._invalidate_session()
        callback(config_value)

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
        self._lang_cache = {}
        self._lang_dir = os.path.join(self.ui_dir, "lang")
        os.makedirs(self._lang_dir, exist_ok=True)

        # seed the translation dictionaries shipped with the release (e.g.
        # en.json, fa.json) into ui_dir/lang/ if the operator has none there
        # yet; existing files are never overwritten, so local edits survive.
        # A deployment that does not want the packaged translations may set
        # GPSMCPMMS_NO_LANG_SEED=1 to skip this.
        packaged_lang = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ui", "lang")
        if (os.path.isdir(packaged_lang) and
                not os.environ.get("GPSMCPMMS_NO_LANG_SEED")):
            for file_name in os.listdir(packaged_lang):
                if not file_name.endswith(".json"):
                    continue
                dest = os.path.join(self._lang_dir, file_name)
                if not os.path.exists(dest):
                    try:
                        shutil.copyfile(
                            os.path.join(packaged_lang, file_name), dest)
                    except OSError as exc:
                        self._logger.error(
                            f"Seeding '{file_name}' failed: {exc}")

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

        if "de" not in self._lang_cache:
            self._lang_cache["de"] = {}

        for lang, lang_dict in self._lang_cache.items():
            lang_dict["lang_cache_modified"] = False
            for key in self.OWN_UI_KEYS:
                if key not in lang_dict:
                    lang_dict[key] = key
                    lang_dict["lang_cache_modified"] = True

    def _harvest_xlation_keys(self, decl_data):
        """
        Collects all German display strings -- labels, tooltips,
        placeholders, acquire-button labels and test messages, including
        those of enum options -- from registered declaration data as keys
        into the translation dictionaries.
        """
        if not isinstance(decl_data, dict):
            return
        for k, v in decl_data.items():
            if k in ("default_val", "fixed_val", "likely_val"):
                continue    # declared values are data, not display strings
            if (k in self.XLATION_DECL_KEYS and
                    isinstance(v, str) and v.strip()):
                self._note_xlation_key(v.strip())
            elif isinstance(v, dict):
                self._harvest_xlation_keys(v)

    def _note_xlation_key(self, xlation_key):
        with self._lock:
            self._active_xlation_keys.add(xlation_key)
            for lang, lang_dict in self._lang_cache.items():
                if xlation_key not in lang_dict:
                    lang_dict[xlation_key] = xlation_key
                    lang_dict["lang_cache_modified"] = True

    def _orphan_keys_of(self, lang_dict):
        # a key is orphaned when no active registration uses it (anymore)
        return sorted(k for k in lang_dict
                      if k != "lang_cache_modified" and
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
                lang_code = "de"
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
                    if k != "lang_cache_modified")):
            return "invalid_dict"

        with self._lock:
            if replace is not None and (
                    replace in ("de", lang) or
                    replace not in self._lang_cache):
                return "invalid_replace"
            if (lang not in self._lang_cache and replace is None and
                    len(self._lang_cache) >= self.MAX_LANGUAGES):
                return "too_many_languages"

            lang_dict = {k: v for k, v in lang_dict.items()
                         if k != "lang_cache_modified"}
            if lang == "de":
                # "de" is the mandatory reference: own keys must survive
                for key in self.OWN_UI_KEYS:
                    lang_dict.setdefault(key, key)
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

    def _translation_of(self, lang, key):
        """The stored translation of `key` in `lang`, or "" if the entry is
        absent or still equals the German key (i.e. untranslated)."""
        with self._lock:
            v = self._lang_cache.get(lang, {}).get(key)
        return v if isinstance(v, str) and v != key else ""

    def _lang_template_csv(self, target, refs):
        """Builds the CSV template for translating into `target`, with a
        column of German source keys, one column per reference language, and
        the target column (pre-filled with any existing translation)."""
        with self._lock:
            existing = set(self._lang_cache)
        refs = [r for r in refs
                if r in existing and r not in ("de", target)][:self.MAX_TEMPLATE_REFS]
        columns = ["de"] + refs + [target]

        buf = io.StringIO()
        # QUOTE_ALL: every field is wrapped in double quotes (RFC 4180) so that
        # punctuation embedded in a key or translation -- notably a semicolon,
        # which German spreadsheets use as their own list separator -- can never
        # be mistaken for a column separator
        writer = csv.writer(buf, delimiter=self.CSV_DELIMITER,
                            quoting=csv.QUOTE_ALL)
        writer.writerow(columns)
        for key in self._active_keys_sorted():
            row = [key]
            row += [self._translation_of(r, key) for r in refs]
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
        if target == "de":
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
        de_idx = header.index("de") if "de" in header else 0
        if target not in header:
            return None, "target_column_missing", None
        tgt_idx = header.index(target)

        with self._lock:
            is_new = target not in self._lang_cache
            over_limit = is_new and len(self._lang_cache) >= self.MAX_LANGUAGES
            removable = sorted(l for l in self._lang_cache if l != "de")
        if over_limit and not (isinstance(remove, str) and remove in removable):
            return None, {"error": "too_many_languages",
                          "removable": removable}, None

        uploaded = {}
        for row in rows[1:]:
            if len(row) <= max(de_idx, tgt_idx):
                continue
            key = row[de_idx].strip()
            if key:
                uploaded[key] = row[tgt_idx].strip()

        active = set(self._active_keys_sorted())
        with self._lock:
            new_dict = {k: v for k, v in self._lang_cache.get(target, {}).items()
                        if k != "lang_cache_modified" and k in active}
        # the uploaded rows edit only the keys they contain: a non-empty cell
        # sets a translation, a blank cell clears one; keys absent from the
        # file keep whatever translation they already had
        for key, value in uploaded.items():
            if key not in active:
                continue
            if value and value != key:
                new_dict[key] = value
            else:
                new_dict.pop(key, None)

        failure = self._store_translation_dict(target, new_dict,
                                               remove if over_limit else None)
        if failure:
            return None, failure, None

        report = self._lang_report_csv(target, active, uploaded, new_dict)
        translated = sum(1 for k in active if k in new_dict)
        return report, translated, len(active)

    def _lang_report_csv(self, target, active, uploaded, new_dict):
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=self.CSV_DELIMITER,
                            quoting=csv.QUOTE_ALL)
        writer.writerow(["de", target, "status"])
        for key in sorted(active):
            value = new_dict.get(key, "")
            if key in uploaded:
                status = ("übernommen" if value else "keine Übersetzung")
            elif value:
                status = "unverändert"
            else:
                status = "nicht in Datei"
            writer.writerow([key, value, status])
        for key, value in uploaded.items():
            if key not in active:
                writer.writerow([key, value,
                                 "übersprungen: unbekannter Schlüssel"])
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
                self._session_token = None
                self._session_admin = False
                return "none"
            return ("valid"
                        if isinstance(token, str) and hmac.compare_digest(
                                token, self._session_token) else
                    "other")

    def _issue_session_token(self):
        timeout = self._session_timeout_seconds()
        with self._lock:
            self._session_token = secrets.token_urlsafe(32)
            self._session_admin = False
            self._session_expires = time.time() + timeout
            return self._session_token

    def _touch_session(self):
        # each valid request restarts the inactivity timer (spec 4.8)
        timeout = self._session_timeout_seconds()
        with self._lock:
            self._session_expires = time.time() + timeout

    def _invalidate_session(self):
        with self._lock:
            self._session_token = None
            self._session_admin = False

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
        thread on the port configured as "config.ui_port".
        """
        from flask import (Flask, Response, abort, jsonify, request,
                           send_from_directory)
        from urllib.parse import urlsplit

        with self._lock:
            if self._editor_started:
                return
            self._editor_started = True

        # seed missing web assets from the packaged defaults, so that a
        # freshly provisioned appliance serves the editor out of the box;
        # assets already present in ui_dir are never overwritten
        packaged_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "ui")
        for asset in ("index.html", "style.css", "app.js"):
            target = os.path.join(self.ui_dir, asset)
            source = os.path.join(packaged_dir, asset)
            if not os.path.exists(target) and os.path.exists(source):
                try:
                    shutil.copyfile(source, target)
                except OSError as exc:
                    self._logger.error(f"Seeding '{asset}' failed: {exc}")

        app = Flask("gpsmcpmms_editor", static_folder=None)

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
            status = self._session_status(token)
            if status == "none":
                # first client without an active session gets the token
                token = self._issue_session_token()
                status = "valid"
            editable = status == "valid"
            if editable:
                self._touch_session()

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
            try:
                result = func()
            except Exception as exc:
                self._logger.error(f"enum provider '{provider}' raised: "
                                   f"{exc}")
                result = "Interner Fehler bei der Wertermittlung"
            if isinstance(result, dict):
                # dynamically delivered labels/tooltips are display strings
                # and hence translation keys, too
                for option in result.values():
                    self._harvest_xlation_keys(
                            option if isinstance(option, dict) else None)
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
            waiter = {"event": event, "value": None}
            with self._lock:
                # a newer capture request replaces an older one on the same
                # path; the replaced request simply runs into its timeout
                self._capture_waiters[path] = waiter
            if event.wait(self.CAPTURE_TIMEOUT):
                return jsonify({"value": waiter["value"]})
            with self._lock:
                if self._capture_waiters.get(path) is waiter:
                    del self._capture_waiters[path]
            return jsonify({"value": None, "timeout": True})

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

        @app.route("/api/lang/info")
        def lang_info():
            editable = self._session_status(request_token()) == "valid"
            if editable:
                self._touch_session()
            with self._lock:
                info = {"languages": sorted(self._lang_cache)}
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
            if not re.fullmatch(r"[a-z]{2,3}", target) or target == "de":
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
            if upload is None or not target:
                abort(400)
            report, result, total = self._apply_lang_csv(
                    target, upload.read(), remove)
            if report is None:
                if isinstance(result, dict):
                    return jsonify(result), 409     # removal choice required
                return jsonify({"error": result}), 400
            resp = _csv_download(report, f"{target}.report.csv")
            resp.headers["X-GPSMCPMMS-Translated"] = str(result)
            resp.headers["X-GPSMCPMMS-Total"] = str(total)
            return resp

        @app.route("/api/end_session", methods=["POST"])
        def end_session():
            if request.headers.get(self.API_HEADER) != "1":
                abort(403)
            if self._session_status(request_token()) != "valid":
                return jsonify({"ended": False}), 401
            self._invalidate_session()
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
