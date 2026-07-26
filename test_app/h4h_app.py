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

"""Main test app for the GPSMCPMMS config-editor (spec section 5.6).

Wires the client modules together, initializes the LED states, registers the
"app" config params, launches the config-editor and keeps the process alive
so that the editor can be exercised.

Run with:  python h4h_app.py
Set H4H_SIMULATE_CARDS=1 to emulate the PN532 delivering a card UID every few
seconds (stands in for the real NFC-reader thread on the appliance).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config_mgr

# inject the application logger as early as possible (spec 5.2)
import logger
config_mgr.switch_to_app_logger(logger.h4h_logger)

import led
import sip                      # noqa: F401  (registers the "sip" module)
import h4h_client               # noqa: F401  (registers the "h4h" module)


SUPPORTED_STATES = [
    {"id": "off", "label": "Aus", "conf": {
        "is_continuous": True, "rgb": (0, 0, 0), "brightness": 0.0}},
    {"id": "booting", "label": "Wird Hochgefahren", "conf": {
        "is_continuous": True, "rgb": (255, 253, 85),
        "brightness": 0.03, "animation": "rotate", "step_on_time": 0.08}},
    {"id": "admin_config", "label": "Basiseinstellungen ausstehend", "conf": {
        "is_continuous": True, "rgb": (255, 253, 85), "brightness": 0.03}},
    {"id": "use_config", "label": "Personalisierung ausstehend", "conf": {
        "is_continuous": False, "rgb": (255, 253, 85), "brightness": 0.03}},
    {"id": "card_reading", "label": "Kartenleser bereit", "conf": {
        "is_continuous": True, "rgb": (24, 178, 92), "brightness": 0.05}},
    {"id": "service_requesting", "label": "Serviceanfrage aktiv", "conf": {
        "is_continuous": False, "rgb": (24, 178, 92), "brightness": 0.05}},
    {"id": "phone_ready", "label": "Freisprecher bereit", "conf": {
        "is_continuous": True, "rgb": (36, 57, 178), "brightness": 0.1}},
    {"id": "phone_active", "label": "Freisprecher aktiv", "conf": {
        "is_continuous": False, "rgb": (36, 57, 178), "brightness": 0.1}},
    {"id": "connectivity_error", "label": "Erreichbarkeitsfehler", "conf": {
        "is_continuous": True, "rgb": (179, 8, 51), "brightness": 0.05}},
    {"id": "action_error", "label": "Aktionsfehler", "conf": {
        "is_continuous": False, "rgb": (179, 8, 51), "brightness": 0.1,
        "animation": "blink", "step_on_time": 0.5, "step_off_time": 0.5}},
    {"id": "halting", "label": "Runterfahren", "conf": {
        "is_continuous": True, "rgb": (255, 253, 85), "brightness": 0.1,
        "animation": "blink", "step_on_time": 0.5, "step_off_time": 0.5}},
]


def config_changed(value):
    logger.h4h_logger.debug("app config changed.")


def get_service_list():
    """Dynamic enum provider referenced by app.h4h_sr_cards.*.service_id
    (spec 4.9.1). On the appliance this would query the H4H server."""
    return {
        "einkauf": {"label": "Einkaufshilfe"},
        "medikamente": {"label": "Medikamentenabholung"},
        "begleitung": {"label": "Begleitung"},
        "besuch": {"label": "Besuchsdienst"},
    }


def register_app_params():
    config_mgr.register_params(
        module_id="app",
        module_label="Basiseinstellungen der H4H-App",
        callback=config_changed,
        type_dict={
            "rfid2sid": {
                "rfid": {"label": "RFID der Servicekarte",
                         "type": "string", "backend_provided": True,
                         "acquire_button": "Karte einlesen"},
                "service_id": {
                    "label": "ID des assoziierten H4H-Servicetyps",
                    "type": "enum", "values": "get_service_list"
                }
            },
            "sr_card_list": {
                "list_member": {"type": "rfid2sid"},
                "list_keys": [["rfid"], ["service_id"]],
                "list_size": "2.."
            }
        },
        param_dict={
            "abort_card_uid": {
                "protected": True, "label": "RFID der Abbruchkarte",
                "type": "string", "backend_provided": True,
                "acquire_button": "Karte einlesen"
            },
            "reboot_card_uid": {
                "protected": True, "label": "RFID der Neustartkarte",
                "type": "string", "backend_provided": True,
                "acquire_button": "Karte einlesen"
            },
            "h4h_sr_cards": {
                "protected": True, "label": "RFID der Service-Karten",
                "type": "sr_card_list"
            },
            "zip": {
                "label": "Postleitzahl des Hilfeleistungsortes",
                "type": "string", "bound_to": r"^\d{5}$"
            }
        },
        func_dict={"get_service_list": get_service_list}
    )


def _simulate_card_reader():
    # stand-in for the PN532 thread: emits a UID matching any card param
    import threading

    def loop():
        n = 0
        while True:
            time.sleep(5)
            n += 1
            config_mgr.handle_value_event(f"04A2{n:04X}B7", [
                "app.abort_card_uid", "app.reboot_card_uid",
                "app.h4h_sr_cards.*.rfid"])
    threading.Thread(target=loop, daemon=True).start()


def main():
    led.ledc.init_supported_states(SUPPORTED_STATES)
    register_app_params()
    config_mgr.start_editor()
    logger.h4h_logger.info(
        f"H4H app bereit; Konfigurationseditor auf Port {config_mgr._ui_port}.")
    if os.environ.get("H4H_SIMULATE_CARDS"):
        _simulate_card_reader()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
