#!/usr/bin/env python3
"""
Interactive demonstration runner for gpsmcpmms with sample modules (logger, led,
sip).
"""

import os
import sys
import time

# Ensure both repository root (for gpsmcpmms) and test_app directory are on
# sys.path
TEST_APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_APP_DIR)

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if TEST_APP_DIR not in sys.path:
    sys.path.insert(0, TEST_APP_DIR)

from gpsmcpmms import config_mgr

# Inject the application logger as early as possible (spec 5.2)
import logger
config_mgr.set_app_context(logger.app_logger, "GPSMCPMMS demo")

import led
import sip  # noqa: F401  (registers the "sip" module)


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


def main():
    led.ledc.init_supported_states(SUPPORTED_STATES)
    config_mgr.start_editor()
    logger.app_logger.info(
        f"App bereit; Konfigurationseditor auf Port {config_mgr._ui_port}."
    )

    print("\n[+] Demo running. Press Ctrl+C to stop.\n")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logger.app_logger.info("Demo stopped by user.")
        print("\n[+] Demo stopped cleanly.")


if __name__ == "__main__":
    main()
