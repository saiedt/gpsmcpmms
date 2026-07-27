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

"""Central logger for the H4H app (spec section 5.2).

Provides the ready-to-use singleton `h4h_logger` and registers the "log"
config module. The main app injects h4h_logger into config_mgr via
config_mgr.switch_to_app_logger(h4h_logger).
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpsmcpmms import config_mgr

h4h_logger = logging.getLogger("h4h")
if not h4h_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] (%(name)s): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"))
    h4h_logger.addHandler(_handler)
    h4h_logger.setLevel(logging.INFO)

_file_handler = None


def _apply_log_file(path):
    global _file_handler
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        new_handler = logging.FileHandler(path, encoding="utf-8")
        new_handler.setFormatter(logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] (%(name)s): %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        if _file_handler is not None:
            h4h_logger.removeHandler(_file_handler)
        h4h_logger.addHandler(new_handler)
        _file_handler = new_handler
    except OSError as exc:
        h4h_logger.warning(f"Log-Datei '{path}' nicht nutzbar: {exc}")


def config_changed(value):
    if not isinstance(value, dict):
        return
    level = value.get("log_level")
    if isinstance(level, str) and hasattr(logging, level):
        h4h_logger.setLevel(getattr(logging, level))
    _apply_log_file(value.get("log_file"))
    h4h_logger.debug("Logger-Konfiguration aktualisiert.")


config_mgr.register_params(
    module_id="log",
    module_label="Logger",
    callback=config_changed,
    param_dict={
        "log_file": {
            "protected": True, "label": "Die Log-Datei", "type": "path",
            "default_val": os.path.expanduser("~/log/h4h.log")
        },
        "log_level": {
            "label": "Detailstufe der Protokollierung",
            "type": "enum", "default_val": "INFO",
            "values": {
                "DEBUG": {"label": "Diagnose"},
                "INFO": {"label": "Hinweis"},
                "WARNING": {"label": "Warnung"},
                "ERROR": {"label": "Fehler"},
                "CRITICAL": {"label": "Kritischer Zustand"}
            }
        }
    }
)
