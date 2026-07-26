# GPSMCPMMS

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**General-Purpose Shared Management of Configuration Parameters in a Multi-Module Setup**

A backend subsystem (`config_mgr`) that lets independent modules register their
configuration parameters — with types, constraints and UI metadata — and then:

- keeps the **single source of truth** for every parameter's *current value*,
- **persists** those values across runs,
- serves a **built-in web config-editor** that collects and validates user input,
- lets modules **query** their values and ask whether their configuration is ready.

It is designed for a zero-maintenance appliance on a trusted LAN, but the core is
generic.

---

## Quick start

```bash
git clone https://github.com/saiedt/gpsmcpmms
cd gpsmcpmms
pip install -r requirements.txt          # Flask; needs Python 3.10+
```

Register a parameter and launch the editor:

```python
# demo.py  (run from the repository root)
from config import config_mgr

config_mgr.register_params(
    module_id="led", module_label="Status display",
    callback=lambda value: print("led:", value),
    param_dict={
        "num_leds": {"label": "Number of LEDs", "type": "int",
                     "bound_to": "1..1000", "default_val": 24},
    },
)

config_mgr.start_editor()                 # serves http://<this-host>:8080/
input("editor running — press Enter to stop\n")
```

Open `http://localhost:8080/` in a browser and edit **Number of LEDs**. The web
assets are served from `ui/`, so run this from a checkout. (Protected parameters
would require the admin password; there are none in this demo.)

---

## Deployment model

The device is a rented, zero-maintenance appliance reachable only on the local
network (no public IP, no login, no user database). Its lifecycle has two phases:

- **Provisioning** — the distributor sets and locks the *protected* first-level
  parameters, then changes the admin password (`ui_passwd`) from its factory
  default.
- **Operation** — the customer edits the *unprotected* parameters. Protected
  parameters stay hidden until the admin password is supplied.

Editing is guarded by a single shared password and an **exclusive single-session
token** (see [Security & sessions](#security--sessions)).

---

## Core concept: structured keys + Declarations

Every configuration parameter is addressed by a dot-separated **path**:

```
<module>.<param>(.<sub>)*
```

- **Level 0** is the module (client) id; **level 1** is a top-level parameter of
  that module. Deeper levels are introduced automatically by **dict** and **list**
  values.
- Each named path element carries a **Declaration** — a small dict of metadata
  that drives both backend validation and the editor's UI.
- **List members** are addressed by zero-padded ordinal ids `00`…`99` and need no
  Declaration of their own (all members share the list's member declaration).
- Element ids match `^[-0-9A-Za-z_]+$` (no dots; must not start with `list_`).

A module describes itself with two dicts:

- **`param_dict`** — maps each level-1 parameter name to its Declaration.
- **`type_dict`** — declares the named **complex types** (dict and list types)
  used to introduce deeper levels, so Declarations are never nested inside one
  another.

---

## Registering parameters

```python
config_mgr.register_params(
    module_id, module_label, param_dict, callback,
    type_dict=None, module_tooltip=None, func_dict=None)
```

- Called **once per run** per module (register the same schema every run; only
  *values* are persisted, never the schema).
- `callback(value)` is invoked immediately with the module's initial values, and
  again whenever the editor commits a change to that module.
- `func_dict` maps function names referenced in Declarations (dynamic enums, see
  [Advanced features](#advanced-features)) to callables.

**Value priority** (highest wins): `fixed_val` → saved user input → `default_val`
→ *no value* (`None`).

Other API methods:

| Method | Purpose |
|--------|---------|
| `query(path)` | `{absolute_path: value}` for the nodes the path matches (module-rooted; wildcards allowed). |
| `config_ready(path=None)` | `True` if no *relevant* leaf under the match is still unset. `None`/`""`/`"*"` = whole tree. Skips empty min-0 lists and fields whose relevance condition is false. |
| `protected_params_ready()` | Like `config_ready`, restricted to `protected` parameters. |
| `handle_value_event(value, alt_target_paths)` | Deliver a backend-captured value to a waiting editor (see 4.9.3). |
| `switch_to_app_logger(logger)` | Inject the application logger (once per run). |

---

## Declaration reference

A Declaration is a dict with any of these keys (`type` is mandatory):

| Key | Meaning |
|-----|---------|
| `type` | A primitive type (below) or a named type from `type_dict`. |
| `label` | Display label. German text doubles as the translation key. |
| `tooltip` | Hover help. |
| `placeholder` | HTML-style placeholder for an input field. |
| `default_val` | Initial value; may be overwritten by the user. |
| `fixed_val` | Constant, protected from change. On a dict/list it locks only the structure/length — inner leaves stay editable unless they lock themselves. |
| `init_only` | Once set (by user or an inherited `fixed_val`), never changes. Only allowed if neither `fixed_val` nor `default_val` is present. |
| `likely_val` | A suggested value shown when there is no `fixed_val`/`default_val`. |
| `relevance` | `"<sibling><op><value>"`. When false, this parameter is hidden and need not have a value. |
| `hidden` | Hide from the editor. |
| `protected` | Hidden until the admin unlocks with the password. |
| `backend_provided` | Value is captured by backend logic (e.g. an NFC reader), read-only in the editor. Requires `acquire_button`; may combine with `init_only`. |

**Primitive types**

| `type` | Value |
|--------|-------|
| `boolean` | `True` / `False` |
| `int`, `float` | numbers; accept `bound_to` and `s2g_scale` |
| `string` | text; accepts `bound_to` (a regex) |
| `password` | text, masked in the editor |
| `url` | a URL string |
| `path` | a file/folder path (existence checked by the editor) |
| `pingable` | a host/IP whose reachability is checked by the editor |
| `color` | a Python `tuple` `(r, g, b)`, each `0..255` (one atomic value) |
| `enum` | one of declared options; requires `values` |

**Type-specific sub-properties**

| Property | For | Meaning |
|----------|-----|---------|
| `values` | `enum` | `{id: {"label": …, "tooltip"?: …}}`, or a **function name** (resolved via `func_dict`) for dynamic options. |
| `bound_to` | `int`/`float` | `"min..max"` (either side omittable). |
| `bound_to` | `string` | a Python regular expression (without the leading `r`). |
| `s2g_scale` | `int`/`float` | `"*N"` or `"/N"` — the editor shows the value scaled and stores it unscaled (UI only). |
| `acquire_button` | `backend_provided` | label of the capture button. |
| `test_func`, `test_func_msg` | any | a callable + a modal message → the editor shows a **Test** button (see 4.9.4). |

**`relevance` operators:** `==`, `!=`, `<`, `>`, `<=`, `>=`, `~=` (regex match).
The right-hand `<value>` is JSON.

---

## Named types (`type_dict`)

A key in `type_dict` declares either a **dict type** or a **list type**:

- **Dict type** — `name → { property: Declaration, … }`. Each property becomes a
  deeper path level. The name must **not** end with `_list`, and no property name
  may start with `list_`.
- **List type** — the name **ends with `_list`** and the value may contain only:

  | Key | Meaning |
  |-----|---------|
  | `list_member` | **required** — a (type-only) Declaration shared by all members. |
  | `list_size` | `"min..max"` inclusive member counts; default `"0..100"`; max 100. |
  | `list_keys` | uniqueness groups, e.g. `[["a"], ["b","c"]]` (a standalone key `a`, plus a compound key `b+c`). |

Named types can be reused across parameters. `param_dict` itself is merged in as a
dict type named after the `module_id`.

---

## Paths, wildcards & queries

Any slot of a path may be a wildcard:

- `*` — matches every child at that level.
- `<prop><op><value>` — a predicate selecting the child(ren) whose `prop` value
  satisfies the condition.

```
led.supported_states.*.id=="booting".conf
```

traverses the `supported_states` list, selects the member whose `id` is
`"booting"`, and resolves to its `conf` sub-structure.

---

## Persistence

Only **values** are persisted (schema is rebuilt every run), **per module**:

- The `SYNC` phase atomically writes `${cvv_dir}/<module>/mod_tree.dump`
  (`{"saved_at": …, "value": …}`), keeping the previous checkpoint as `*.old`.
- Verified updates are also appended to a write-ahead journal
  `leaf_update.log`; on load, journal entries newer than the checkpoint are
  replayed — so an update is crash-safe between two syncs. A successful sync
  resets the journal.

---

## Internal representation (the cvv tree)

The current-values view and its schema metadata live in one tree, implemented in
`cvv_tree.py` and exposed to `config_mgr` through classmethods of `CvvNode`
(`register`, `set_logger`, `init_module`, `update_module`, `query`,
`config_ready`, `protected_params_ready`, `get_cvv_json_dump`).

- One `CvvNode` root; every path element is a `CvvPathElem`; each owns a
  `CvvValue` holding its constraints, relevance rules, configurability and value.
- A **leaf** holds a simple value; an inner node's value is the dict or list
  composed from its children.
- A **list node** is its own list root; its children are the ordinal members,
  plus one hidden item template (`_list_item_template`) exported to the editor as
  `item_template`.
- Each module runs its pipeline under a **per-module lock** through ordered
  phases — `init_module`: INIT → LOAD → SYNC; `update_module`: UPDATE → SYNC —
  so independent modules run in parallel while same-module operations serialize.

```
cvv_root
├── log                       module node (dict)
│   ├── log_file              leaf ("~/log/app.log")
│   └── log_level             leaf ("INFO")
└── led                       module node (dict)
    ├── num_leds              leaf (24)
    └── supported_states      list node
        ├── [item template]   hidden; exported as "item_template"
        ├── 00                member (dict) → id, label, conf …
        └── 01 …
```

`GET /api/cvv_data` serves a JSON dump: for each node its `path`, `ui`
properties, `constraints`, `configurability`, optional `protected`/`relevance`,
and (by kind) `value`, `children` or `item_template`.

---

## Security & sessions

- **Perimeter only.** Anyone on the LAN can view/edit unprotected parameters; no
  login. Protected parameters require the admin password (`config.ui_passwd`).
- **Exclusive session.** At most one editing token exists at a time. A second
  client is served read-only. The token lives only in the browser's memory,
  expires after an inactivity timeout (`config.session_timeout`, default 30 min),
  is invalidated by any `register_params()`, and is released by **End Session**.
- **Anti-CSRF.** Mutating requests require a custom header and a same-origin
  `Origin`; no cookies are used.
- **Factory-password notice.** While `ui_passwd` still equals the factory default,
  the editor shows a warning and an *Exit Admin Mode* action that forces a change.

**Update semantics.** On `POST /api/config/update` the backend normalizes and
strictly validates each value; valid values are applied and saved, invalid ones
are skipped and their paths returned as `rejected`. Only a wholly-malformed
payload (not a JSON object, unknown module) yields `400`.

---

## The config-editor (web UI)

`config.py` serves a Flask app; the assets `index.html`, `style.css`, `app.js`
are read from `ui_dir`. The UI renders one **collapsible group per module**
(sorted by id), each ending with a **Save** button that commits the module.

- **Dict groups** render one row per property (respecting `hidden` and
  `relevance`), recursing into sub-groups.
- **List editors** come in two shapes: a small **table + value field** for lists
  of simple values, and a **record navigator** (record block + up/down + a *New*
  button + Remove/Undo/Apply) for lists of records.
- Fields validate on leave; `s2g_scale` is applied for display; dynamic enums are
  fetched on expand; already-used enum options are filtered out where a
  `list_keys` uniqueness applies; `backend_provided` fields show an acquire
  button; `test_func` fields show a Test button with a confirmation modal.

---

## Multi-linguality

German is the source language: the German `label`/`tooltip`/`placeholder` strings
**are** the translation keys. Dictionaries live at `ui_dir/lang/<code>.json`;
missing keys fall back to German, so a language may stay partially translated.
Up to **seven** languages may coexist; `de` is mandatory. Corrupt dictionary files
are quarantined and regenerated at startup.

Translations are added/updated through a **CSV round-trip** (no timeouts, easy for
a human or an AI):

1. **Download a template** for the target language — columns: `de` (source/key),
   up to three chosen reference languages, and the target column (pre-filled).
   The file is UTF-8 (with BOM), **pipe-separated (`|`)** and every field is
   **fully quoted** (RFC 4180), so embedded `,`/`;` can never split a row.
2. **Fill it offline**, then **upload** it. Rows are applied one by one
   (non-empty sets, blank clears, absent keeps; unknown keys skipped; unused keys
   pruned). Adding an 8th language prompts which existing one to replace.
3. A **report CSV** is returned with a per-row status and translated/total counts.

---

## REST API (summary)

Static: `GET /`, `GET /style.css`, `GET /app.js`.
Mutating requests carry `X-GPSMCPMMS-Api: 1`; the session token travels in
`X-GPSMCPMMS-Token`.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/cvv_data[?passwd=…]` | Tree dump; issues/refreshes the session token; strips protected subtrees unless unlocked. |
| `POST /api/config/update` | Apply `{module, value}`; returns `{rejected: […]}`. |
| `GET /api/schema[/<lang>]` | Translation dictionary for a language (defaults to `de`). |
| `GET /api/lang/info` | Language list (plus orphan keys for admins). |
| `GET /api/lang/template?lang=&refs=` | Download a translation template (admin). |
| `POST /api/lang/upload` | Upload a filled translation CSV (admin); returns the report, or `409` asking which language to replace. |
| `GET /api/config/enum-options?path=` | Resolve a dynamic enum's options. |
| `GET /api/value/capture?path=` | Long-poll (≤ 30 s) for a backend-captured value. |
| `POST /api/config/test` | Run the `test_func` for `{path, value}`. |
| `POST /api/end_session` | Release the editing token. |

---

## Advanced features

- **Dynamic enums** — `values` may be a function name (in `func_dict`); the editor
  fetches options via `/api/config/enum-options` when the group is expanded. The
  function returns the options dict or an error string that blocks expansion.
- **Backend-captured values** — a `backend_provided` field shows an
  `acquire_button`; pressing it long-polls `/api/value/capture`. A module delivers
  the value with `config_mgr.handle_value_event(value, alt_target_paths)` (use
  `*` in a path to target a list member); unmatched events are no-ops.
- **List uniqueness** — simple-value lists forbid duplicates; `list_keys` declares
  uniqueness for record lists, and the editor hides already-used enum options.
- **Testable parameters** — `test_func` + `test_func_msg` add a Test button and a
  confirmation modal, executed via `/api/config/test`.

---

## Own configuration parameters

`config_mgr` registers a hidden `config` module for its own settings:

| Path | Meaning |
|------|---------|
| `config.ui_passwd` | admin password (factory default until changed) |
| `config.ui_port` | editor port (default 8080) |
| `config.session_timeout` | session inactivity timeout in minutes (default 30) |

The working directories are resolved from `GPSMCPMMS_CVV_DIR` and
`GPSMCPMMS_UI_DIR` (defaults under `~/.config/gpsmcpmms/`).

---

## Examples

*Illustrations of how a module declares its parameters — not a test suite.*

**A flat module** — a couple of simple parameters:

```python
config_mgr.register_params(
    module_id="log",
    module_label="Logger",
    callback=on_change,
    param_dict={
        "log_file": {"label": "Log file", "type": "path",
                     "protected": True, "default_val": "~/log/app.log"},
        "log_level": {"label": "Log level", "type": "enum",
                      "default_val": "INFO",
                      "values": {"DEBUG": {"label": "Debug"},
                                 "INFO":  {"label": "Info"},
                                 "ERROR": {"label": "Error"}}},
    },
)
```

**A list of records** — reusable named types, a fixed list whose inner leaves stay
editable, plus `color`, `s2g_scale`, `enum` and `relevance`:

```python
config_mgr.register_params(
    module_id="led",
    module_label="Status display",
    callback=on_change,
    type_dict={
        "led_conf": {                          # a named dict type
            "rgb": {"label": "Colour", "type": "color"},
            "brightness": {"label": "Brightness", "type": "float",
                           "bound_to": "0..1", "s2g_scale": "*100"},
            "animation": {"label": "Animation", "type": "enum",
                          "default_val": "none",
                          "values": {"none":  {"label": "None"},
                                     "blink": {"label": "Blink"}}},
            "step_ms": {"label": "Pulse (ms)", "type": "float",
                        "s2g_scale": "*1000",
                        "relevance": 'animation!="none"'},
        },
        "led_state": {                         # another named dict type
            "id":    {"type": "string", "hidden": True, "init_only": True},
            "label": {"label": "Name", "type": "string", "init_only": True},
            "conf":  {"label": "Settings", "type": "led_conf"},
        },
        "state_list": {                        # a named list type (ends in _list)
            "list_member": {"type": "led_state"},
            "list_size": "2..",
        },
    },
    param_dict={
        "num_leds": {"label": "Number of LEDs", "type": "int",
                     "bound_to": "1..1000", "default_val": 24},
        "supported_states": {"label": "Supported states", "type": "state_list",
                             "fixed_val": [                 # locks the list
                                 {"id": "off", "label": "Off",
                                  "conf": {"rgb": (0, 0, 0), "brightness": 0.0}},
                                 # …
                             ]},
    },
)
```

A backend-captured field (e.g. an RFID reader) and a dynamic enum would look like:

```python
param_dict={
    "card_uid": {"label": "Service card", "type": "string",
                 "backend_provided": True, "acquire_button": "Scan card"},
    "service_id": {"label": "Service type", "type": "enum",
                   "values": "get_service_list"},   # resolved via func_dict
}
# …register_params(…, func_dict={"get_service_list": get_service_list})
```

---

## Related work & limitations

Python has plenty of configuration tooling, but it is fragmented and no single
popular package covers this exact niche — framework-agnostic self-registration
**plus** an auto-generated web editor **plus** validation, persistence and i18n in
one box. It splits roughly into three camps:

- **Loading & typed validation** — [`pydantic` / `pydantic-settings`](https://docs.pydantic.dev/),
  [`dynaconf`](https://www.dynaconf.com/), [`hydra`](https://hydra.cc/) + `omegaconf`,
  `confuse`, and [`traitlets`](https://traitlets.readthedocs.io/) (typed *and*
  observable). These give you a schema and values; none render an editor.
- **Runtime-editable config with a UI** — Home Assistant's *config flows* (declare
  a schema → auto-generated UI → validated → persisted; the closest analog in
  spirit, but embedded in Home Assistant, not a reusable library) and
  [Django Constance](https://django-constance.readthedocs.io/) (runtime settings in
  the Django admin, but flat and Django-coupled). On the frontend, the
  "schema → form" idea is well established via
  [JSON Schema Form (RJSF)](https://rjsf-team.github.io/react-jsonschema-form/) and
  `json-editor`.
- **Distributed config & feature flags** — Consul, etcd, Vault; Unleash, Flagsmith,
  LaunchDarkly. Powerful, but they need a server/service and target fleets, not a
  single offline device.

### What this project adds

A self-contained *declare → auto-generate editor → validate → persist → notify*
subsystem with no external service, tuned for an offline LAN appliance edited by
non-technical users:

- a **UI-aware** declaration language (labels, tooltips, `relevance`, display
  scaling, `likely_val`, dynamic enums) — richer than value-focused loaders;
- **structured editing** of nested dicts and **lists of records** in the generated
  UI (most runtime-config UIs, Constance included, are flat key→value);
- **domain features** rarely bundled together: hardware-captured values via
  long-poll, `test_func` buttons, per-module change callbacks;
- an **appliance security/workflow** model (single shared password, exclusive
  session, factory-password nudge) and an AI-friendly CSV translation round-trip.

### Limitations & non-goals

Deliberate trade-offs for a trusted-LAN appliance:

- **Security is intentionally minimal** — one shared password, first-connect
  session token, no per-user authentication, no TLS assumed, no audit log. Safe
  only inside a trusted network.
- **A bespoke validation DSL and hand-written UI**, rather than reusing Python's
  type system with **JSON Schema** and an existing form generator. This trades
  ecosystem leverage (mature validators, JSON-Schema/OpenAPI interop, tooling) for
  domain control.
- **Single process, single device, single active editor** — no layered config
  sources or `${var}` interpolation, no distributed consistency, no fleet-wide
  hot-reload, and no schema versioning/migration across releases.
- **Maturity** — a purpose-built component, not a battle-tested library with a
  large test suite, a security process and a community behind it.

### When to use something else

| Need | Better fit |
|------|-----------|
| Typed application settings | `pydantic-settings` |
| Layered / multi-source config | `dynaconf`, `hydra` |
| Flat runtime settings inside a Django app | Django Constance |
| Distributed / fleet config, feature flags | Consul / etcd, Unleash / Flagsmith |
| A schema-driven form without a custom DSL | JSON Schema + RJSF |

For its actual target — an **offline appliance where non-technical users edit
rich, structured, hardware-linked configuration through a browser on a trusted
LAN, in several languages** — there is no drop-in open-source equivalent; Home
Assistant's config flows come closest but are not extractable as a standalone
library.

---

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) (attribution in [NOTICE](NOTICE)).

Copyright 2026 saiedt
