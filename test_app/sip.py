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

"""Telephony / speakerphone module of the H4H app (spec section 5.4).

The actual SIP/PJSIP logic is skipped for the test app; only the config
params are registered.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config_mgr


def test_autoanswer(value):
    # would call the configured number to test the auto-answer chain
    return True


def config_changed(value):
    pass


config_mgr.register_params(
    module_id="sip",
    callback=config_changed,
    module_label="Telefonie- & Freisprecher-Einstellungen",
    type_dict={
        "sip_login": {
            "server": {
                "label": "SIP-Server", "likely_val": "sip.easybell.de",
                "tooltip": "Server-IP bzw. -URL des SIP-Providers.",
                "type": "pingable"
            },
            "user": {
                "label": "Telefonnummer", "placeholder": "004961501834300",
                "tooltip": "Eine im öffentlichen Telefonnetz erreichbare "
                         + "Telefonnummer als Benutzername.",
                "type": "string", "bound_to": r"^\d{10,}$"
            },
            "passwd": {
                "label": "Passwort", "type": "password"
            }
        },
        "service_addr": {
            "host": {
                "label": "Host-IP", "type": "pingable"
            },
            "port": {
                "label": "Host-Port", "type": "int",
                "bound_to": "100..65535"
            }
        },
        "spph": {
            "requires_softphone": {
                "label": "Softphone erforderlich", "type": "boolean",
                "tooltip": "Falls die Hardwarelösung nicht als SIP-Client "
                         + "fungieren kann, muss diese Option aktiviert "
                         + "werden, damit ein Softphone Anrufe entgegen "
                         + "nimmt."
            },
            "extension": {
                "label": "Teilnehmer-Durchwahl", "bound_to": r"^\d{2,4}$",
                "tooltip": "Durchwahlnummer des Freisprechers als Teilnehmer"
                         + " bei lokaler Telefonanlage.", "type": "string"
            },
            "passwd": {
                "label": "Teilnehmer-Passwort", "type": "password",
                "relevance": "requires_softphone==true",
                "tooltip": "Passwort des Freisprechers als Teilnehmer bei "
                         + "lokaler Telefonanlage."
            },
            "inbound_port": {
                "label": "Teilnehmer-Port", "bound_to": "100..65535",
                "type": "int", "relevance": "requires_softphone==true",
                "tooltip": "Portnummer, unter der die lokale Telefonanlage "
                         + "den Freisprecher erreichen kann."
            },
            "initial_standby_duration": {
                "label": "Initial-Bereitschaftsdauer (Minuten)",
                "type": "int", "s2g_scale": "/60",
                "tooltip": "Maximale Bereitschaftsdauer der automatischen "
                         + "Rufannahme für den 1. Anruf nach Aktivierung."
            },
            "extended_standby_duration": {
                "label": "Folge-Bereitschaftsdauer (Minuten)",
                "type": "int", "s2g_scale": "/60",
                "tooltip": "Maximale Bereitschaftsdauer der automatischen "
                         + "Rufannahme für die Anrufe nach dem ersten Anruf."
            },
            "max_standby_extensions": {
                "label": "Max. Folgegespräche", "type": "int",
                "tooltip": "Für jede Serviceanfrage kann es nach einem "
                         + "Initialgespräch maximal so viele Folgegespräche "
                         + "geben.", "bound_to": "0..5"
            }
        }
    },
    param_dict={
        "global_sip_provider": {
            "protected": True, "label": "Öffentlicher SIP-Zugang",
            "tooltip": "Zugang zum öffentlichen Telefonnetz über das SIP-"
                     + "Protokoll.",
            "type": "sip_login", "test_func": test_autoanswer,
            "test_func_msg": "Die eingestellte Telefonnummer kann angerufen "
                           + "werden, um die gesamte Kette bis zur automatischen "
                           + "Rufannahme zu testen, falls auch die Einstellungen "
                           + "der lokalen IP-Telefonanlage und die des lokalen "
                           + "Freisprechers stimmen."
        },
        "local_sip_provider": {
            "protected": True, "label": "Lokale IP-Telefonanlage",
            "tooltip": "Adresse und Portnummer der lokalen Telefonanlage, "
                     + "die zwischen dem öffentlichen SIP-Server und dem lokalen"
                     + " Freisprecher sitzt.", "type": "service_addr",
            "default_val": {"host": "127.0.0.1", "port": 5080}
        },
        "speakerphone": {
            "protected": True, "label": "Lokaler Freisprecher", "type": "spph",
            "tooltip": "Der lokale Freisprecher mit automatischer Rufannahme bei"
                     + " berechtigt eingehenden Anrufen.", "default_val": {
                "passwd": "FS-Int_HF-Dev", "max_standby_extensions": 2,
                "extension": "00", "initial_standby_duration": 3600,
                "inbound_port": 5062, "extended_standby_duration": 1800
            }
        }
    }
)
