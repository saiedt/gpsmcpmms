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

"""Hub4Help REST client of the H4H app (spec section 5.5).

The actual REST logic is skipped for the test app; only the config params
are registered.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import config_mgr


def test_settings(value):
    # would probe the H4H server for reachability with the given key
    return True


def config_changed(value):
    pass


config_mgr.register_params(
    module_id="h4h",
    module_label="Hub4Help REST-Schnittstelle",
    callback=config_changed,
    param_dict={
        "base_url": {
            "protected": True, "label": "H4H-API Basis-URL", "type": "url",
            "default_val": "https://api-partner.h4h.staging.cosynus.de"
        },
        "service_key": {
            "protected": True, "label": "H4H-API Service-Key",
            "type": "password", "test_func": test_settings,
            "test_func_msg": "Mit dem bereitgestellten Schlüssel für den Zugriff "
                           + "auf die eingestellten Basis-URL wird die "
                           + "Erreichbarkeit und Bereitschaft des H4H-Servers "
                           + "getestet..."
        }
    }
)
