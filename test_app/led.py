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

"""LED status ring controller for the H4H app (spec section 5.3).

Declares LEDController with the singleton `ledc`. The config params are
registered only when ledc.init_supported_states() is called (by h4h_app.py),
because the set of supported states is a fixed_val provided at that point.
The actual LED driving (set_state) is not relevant for the test app.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpsmcpmms import config_mgr

try:
    # only available on the target appliance (NeoPixel ring on GPIO10)
    import board
    import neopixel
    _HARDWARE = True
except Exception:
    _HARDWARE = False


def test_conf_value(value):
    """Briefly realizes the given led_state_conf for a visual check
    (spec 4.9.4); the test app only acknowledges the request."""
    ledc.set_state(value)
    return True


class LEDController:
    def __init__(self):
        self.states_initialized = False
        self._supported_states = []
        self._pixels = None

    def init_supported_states(self, led_state_list):
        if self.states_initialized:
            return
        self.states_initialized = True

        config_mgr.register_params(
            module_id="led",
            module_label="Statusanzeige",
            callback=config_changed,
            type_dict={
                "led_state_conf": {
                    "num_active_leds": {
                        "label": "Aktive LEDs", "type": "int",
                        "default_val": 32,
                        "tooltip": "Im Normalfall werden die Zustände mit einem "
                                 + "internen LED-Ring mit 24 LEDs realisiert; "
                                 + "in dem Falle sollte für alle Modi der "
                                 + "Defaultwert unverändert bleiben. Bei "
                                 + "externen LED-Streifen mit z.B. 300 LEDs "
                                 + "kann für beliebige Modi ein zentrierter "
                                 + "Teilbereich für die Realisierung von Modi "
                                 + "herangezogen werden; die Zahl hier bestimmt "
                                 + "die Länge dieses Teilbereiches. Wenn diese "
                                 + "Zahl größer ist als die Zahl der vorhandenen"
                                 + " LEDs, verursacht das keinen Fehler, weil "
                                 + "dann sowieso alle LEDs herangezogen werden."
                    },
                    "is_continuous": {
                        "label": "Durchgehend?",
                        "type": "boolean", "default_val": True,
                        "tooltip": "Falls verneint, werden zwei Bögen bzw. "
                                  + "Striche in dem aktiven Bereich gerendert."
                    },
                    "rgb": {
                        "label": "Farbe", "type": "color"
                    },
                    "brightness": {
                        "label": "Helligkeit", "type": "float",
                        "bound_to": "0..1", "s2g_scale": "*100",
                        "tooltip": "Die Helligkeit der LEDs; um Stromversorgung "
                                 + "zu schonen, wird eine Zahl kleiner als 21 "
                                 + "empfohlen; oft reicht ein Wert unter 10."
                    },
                    "animation": {
                        "label": "Animation", "type": "enum", "values": {
                            "none": {"label": "Keine"},
                            "blink": {"label": "Blinken"},
                            "rotate": {"label": "Rotieren"}
                        },
                        "default_val": "none"
                    },
                    "step_on_time": {
                        "label": "Impulsdauer (Millisekunden)", "type": "float",
                        "s2g_scale": "*1000", "relevance": "animation!=\"none\"",
                        "tooltip": "Beim Rotieren wird der Wert 80 empfohlen "
                                 + "und beim Blinken 500."
                    },
                    "step_off_time": {
                        "label": "Pausendauer (Millisekunden)", "type": "float",
                        "s2g_scale": "*1000", "likely_val": 0.5,
                        "relevance": "animation==\"blink\"",
                        "tooltip": "Relevant nur beim Blinken: für so lange "
                                 + "bleiben alle LEDs aus."
                    }
                },
                "led_state": {
                    "id": {
                        "hidden": True, "type": "string", "init_only": True
                    },
                    "label": {
                        "label": "Bezeichnung", "type": "string",
                        "init_only": True
                    },
                    "conf": {
                        "label": "Einstellungen", "type": "led_state_conf",
                        "test_func": test_conf_value,
                        "test_func_msg": "Der gewünschte LED-Zustand wird zwecks "
                                       + "Überprüfung der aktuellen Einstellungen "
                                       + "hergestellt..."
                    }
                },
                "led_state_list": {
                    "list_member": {"type": "led_state"},
                    "list_size": "2.."
                }
            },
            param_dict={
                "num_leds": {
                    "label": "Gesamtzahl der LEDs", "type": "int",
                    "bound_to": "24..1000", "default_val": 24
                },
                "supported_states": {
                    "label": "Unterstützte Zustände", "type": "led_state_list",
                    "fixed_val": led_state_list
                }
            }
        )

    def set_state(self, led_state):
        # implementation not relevant for the test app
        pass


def config_changed(value):
    if isinstance(value, dict):
        ledc._supported_states = value.get("supported_states", [])


ledc = LEDController()
