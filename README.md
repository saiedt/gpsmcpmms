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

This README is the reference: what exists and how it behaves. Three guides sit
beside it, each for a different pair of hands:

| Guide | For |
|-------|-----|
| [Building an application](docs/developer-guide.md) | Developers — practices worth having, and the release-making pass at the end. |
| [Translation guide](docs/translation-guide.en.md) ([de](docs/translation-guide.de.md)) | Whoever fills in a language, with or without an AI assistant. |

---

## Quick start

```bash
pip install .          # from a checkout of this repo (Python 3.10+; pulls in Flask)
```

> **Deploying over git? Bump the version first.** `pip install git+https://…`
> compares the *version* in the cloned metadata against what is installed — not
> the commit. With an unchanged number it clones, reads the metadata and then
> quietly does nothing, leaving the old code in place and no error to notice.
> The version lives in `gpsmcpmms/__init__.py`; `pyproject.toml` reads it from
> there, so there is one place to change. To reinstall the same version on
> purpose, use `--force-reinstall --no-deps`.

Register a parameter and launch the editor:

```python
# demo.py
from gpsmcpmms import config_mgr

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
assets ship inside the package, so this works from anywhere once installed.
(Protected parameters would require the admin password; there are none in this
demo.)

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
| `handle_value_event(value, alt_target_paths)` | Deliver a backend-captured value to a waiting editor; `True` if one took it (see 4.9.3). |
| `note_xlation_keys(*keys, kind=None)` | Register display strings a module only uses at runtime, so they reach the translation templates. `kind` says what they are — pass `"speech"` for anything read aloud, which nothing else could tell a translator. |
| `add_original_xlations(xlation_lang, xlations)` | Supply translations for keys already noted, taken from where their wording came: `xlations` maps each key to its reading in `xlation_lang`. Never overwrites, never invents a language, refuses unregistered keys. See [Strings that arrive in another language](#strings-that-arrive-in-another-language). |
| `translate(key, lang)` | The `lang` rendering of such a string, falling back to the key itself. Accepts `de` or `de-DE`. |
| `switch_to_app_logger(logger)` | Inject the application logger (once per run). |
| `discard_module(module_id)` | The module has no parameters any more: the declaration is dropped and everything persisted for it is deleted. See [Giving up a module's parameters](#giving-up-a-modules-parameters). |

---

## Declaration reference

A Declaration is a dict with any of these keys (`type` is mandatory):

| Key | Meaning |
|-----|---------|
| `type` | A primitive type (below) or a named type from `type_dict`. |
| `label` | Display label. The text doubles as its own translation key. |
| `tooltip` | Hover help. |
| `placeholder` | HTML-style placeholder for an input field. |
| `default_val` | Initial value; may be overwritten by the user. |
| `fixed_val` | Constant, protected from change. On a dict/list it locks only the structure/length — inner leaves stay editable unless they lock themselves. |
| `init_only` | Once set (by user or an inherited `fixed_val`), never changes. Only allowed if neither `fixed_val` nor `default_val` is present. |
| `likely_val` | A proposal. Like `default_val`, but the backend does not adopt it: the parameter stays unset, so `config_ready()` stays false until someone confirms it. The editor fills the field in, and saving the module is that confirmation. |
| `relevance` | `"<sibling><op><value>"`. When false, this parameter is hidden and need not have a value. |
| `hidden` | Hide from the editor. |
| `protected` | Hidden until the admin unlocks with the password. |
| `backend_provided` | Value is captured by backend logic (e.g. an NFC reader), read-only in the editor. Requires `acquire_button`; may combine with `init_only`. |
| `hint` | A statement about how things stand, shown **above** the field. Either literal text, or the name of a `func_dict` entry making it dynamic — see *Hints* under [Advanced features](#advanced-features). Not a tooltip: a tooltip explains and never expires, a hint reports and can stop being true. |

**Primitive types**

| `type` | Value |
|--------|-------|
| `boolean` | `True` / `False` |
| `int`, `float` | numbers; accept `bound_to` and `s2g_scale` |
| `string` | text; accepts `bound_to` (a regex) |
| `file` | the bare **name** of a file in a directory the host names with `file_dir`; see *Files* under [Advanced features](#advanced-features) |
| `password` | text, masked in the editor |
| `url` | a URL string |
| `path` | a file/folder path, checked against the device's file system (see below) |
| `pingable` | a host/IP whose reachability the editor checks (see below) |
| `color` | a Python `tuple` `(r, g, b)`, each `0..255` (one atomic value) |
| `enum` | one of declared options; requires `values` |

> **Give a `boolean` a `default_val`.** Any unset leaf keeps `config_ready()`
> false, and a boolean is the one case the user cannot see: unset renders
> exactly like `False`. The editor therefore draws an unanswered checkbox in its
> *indeterminate* state and, on save, asks once whether the unanswered options
> should count as "no" — but a declared default spares that question entirely.
> When the decision genuinely has to be made by hand, a two-option `enum` states
> both alternatives instead of leaving the user to infer the negative.

**Type-specific sub-properties**

| Property | For | Meaning |
|----------|-----|---------|
| `values` | `enum` | `{id: {"label": …, "tooltip"?: …}}`, or a **function name** (resolved via `func_dict`) for dynamic options. |
| `values_for` | dynamic `enum` | Name of a sibling whose current value the options are computed *for*; it is passed to the provider. See *Dynamic enums* under [Advanced features](#advanced-features). |
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

The current-values view (CVV) and its schema metadata live in one tree,
implemented in `gpsmcpmms/cvv_tree.py` and exposed to `config_mgr` through
classmethods of `CvvNode` (`register`, `set_logger`, `init_module`,
`update_module`, `query`, `config_ready`, `protected_params_ready`,
`get_cvv_json_dump`).

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
- **Taking it back.** Because the token is memory-only, closing the window — or
  merely reloading the page — abandons a session that the device still considers
  live, locking the admin out of their own editor until it times out. The
  read-only banner therefore offers **Take over session**, which reclaims the
  lock on proof of the admin password and invalidates the previous token. The
  new session starts **in admin mode**: only an admin can take a session over at
  all, so handing back a read-only editor that immediately demands the same
  password again would ask one question twice and answer neither. Every
  transition of the lock — granted, refused, taken, ended, expired — is logged
  with the client's address.
- **Anti-CSRF.** Mutating requests require a custom header and a same-origin
  `Origin`; no cookies are used.
- **Factory-password notice.** While `ui_passwd` still equals the factory default,
  the editor shows a warning banner. In admin mode the banner also offers *Exit
  admin mode*, which asks for a new password and will not complete until one is
  given — cancel it and admin mode simply stays open. It is a prompt, not an
  enforcement: *End session* leaves without asking, so a distributor who never
  uses the banner's button is never stopped.

**Update semantics.** On `POST /api/config/update` the backend normalizes and
strictly validates each value; valid values are applied and saved, invalid ones
are skipped and their paths returned as `rejected`. Only a wholly-malformed
payload (not a JSON object, unknown module) yields `400`.

---

## The config-editor (web UI)

Beside serving as the interface between client modules and the system,
`gpsmcpmms/config.py` houses the Flask application backend that exposes the REST
API summarized further below. The assets `index.html`, `style.css`, `app.js` are
served from `ui_dir`, into which `start_editor()` stages the packaged copies from
`gpsmcpmms/ui/`. It records what it staged in `ui_dir/.staged.json`, so an
upgraded package refreshes an asset that is still untouched — otherwise a
frontend fix would never reach a device — while an asset the deployment has
edited itself is left in place. The UI renders one **collapsible group
per module**, each ending with a **Save** button that commits the module. A group
with nothing to show is left out entirely, which is what happens to a module
whose parameters are all `protected` when no admin is logged in.

**What decides the order on screen** — two rules, and neither is alphabetical by
label:

| Level | Order | How you control it |
|-------|-------|--------------------|
| Module groups | Sorted by `module_id` | Prefix the ids (`0log`, `1sip`, …). Ids are never displayed, so a prefix costs nothing. |
| Everything below | Declaration order, at every depth | Write `param_dict` and each named type in the order you want to see. |

- **Dict groups** render one row per property (respecting `hidden` and
  `relevance`), recursing into sub-groups.
- **List editors** come in two shapes: a small **table + value field** for lists
  of simple values, and a **record navigator** (record block + up/down + a *New*
  button + Remove/Undo/Apply) for lists of records.
- Fields validate on leave; `s2g_scale` is applied for display; dynamic enums are
  fetched on expand; already-used enum options are filtered out where a
  `list_keys` uniqueness applies; unanswered booleans render *indeterminate* and
  are confirmed once on save; `backend_provided` fields show an acquire button
  (which freezes the editor until the value arrives or the wait fails);
  `test_func` fields show a Test button with a confirmation modal.

---

## Multi-linguality

A display string **is** its own translation key: the `label`/`tooltip`/
`placeholder` text as written. Dictionaries live at `ui_dir/lang/<code>.json`;
missing keys fall back to the key itself, so a language may stay partially
translated and still read. Any number of languages may coexist, and none is ever
removed to make room for another. Corrupt dictionary files are quarantined and
regenerated at startup.

**Every key in the tree is written in `DECL_LANG`** — English, so that adopting
this library does not oblige anyone to write German labels and translate them
into their own language. That holds for the host's keys as much as for this
library's, and it is what makes the fallback safe: an untranslated string reads
in English, never in a third language the reader has no reason to know.

Where a module's wording genuinely arrives in another language — a remote
catalogue, a foreign schema — it settles on a `DECL_LANG` wording and hands the
original over as a translation; see
[Strings that arrive in another language](#strings-that-arrive-in-another-language).
Identical strings are one key, whoever registered them.

**Which languages exist here** is governed by two handles, and a language has to
pass **both**:

1. **An allow-list**, `{code: endonym}`, seeded once from
   `ConfigManager.LANGUAGE_OPTIONS` into **`ui_dir/languages.json`** and never
   overwritten again. This is the deployment's upper bound: whatever the release
   happens to ship dictionaries for, only what stands here is offered.
2. **A validator the host registers** — `set_language_validator(fn)`, where
   `fn(code)` returns whether that language is acceptable. Use this when the host
   knows something the library cannot. An appliance that reads its texts aloud has
   no use for a language its speech service has no voice for: without the check,
   somebody translates several hundred strings and discovers only afterwards that
   none of them can be spoken. That knowledge belongs to the host — the library has
   no business knowing which speech service exists.
   A validator that raises counts as consent, and the protected languages are
   accepted regardless. Refusing to let a device be configured because a check was
   itself unavailable is the worse failure.

The two narrow, and neither overrules the other: the list belongs to whoever
installs the device, the validator to whoever wrote the host. A validator used to
replace the list, which made the list dead weight for every host that installs one
— an operator could strike a language out and be handed it straight back, and on an
appliance whose validator says yes whenever its speech service is unreachable, that
is every language.

> **Edit the file, not the constant.** Under a virtualenv the constant lives in
> `.venv/lib/python3.x/site-packages/gpsmcpmms/config.py` — awkward to reach, and
> the edit disappears at the next `pip install --upgrade`. `ui_dir/languages.json`
> is yours, survives upgrades, and is read at every start. An unreadable file falls
> back to the shipped list rather than to none.

Both handles govern which languages are **offered**, not which dictionaries are
loaded: a dictionary on disk for a language nobody allows is read, kept and simply
not offered — it costs nothing and is ready the day somebody allows it. Discarding a
deployment's translations at startup because a rule changed later would destroy work
nobody can get back.

`DECL_LANG` is complete by construction, with or without a dictionary: the keys
are already written in it. For every other language **an absent entry means
untranslated and any entry counts as translated** — including one that reads exactly like the key, which is
how a translator records that a string stays as it is. Some words are the same in
two languages ("OK" is Polish for OK) and some strings are not sentences at all,
like the placeholder showing the shape of a phone number; without this they could
never be settled, and their language would stay incomplete for ever.

> **Dictionary format 2.** Until format 1 every known key was written into every
> dictionary as its own value, and *that* was how "untranslated" was recorded — so
> the two meanings could not coexist. A dictionary without the `lang_format`
> marker is migrated once on load: entries that merely repeat their key are
> dropped and the marker is set. The cost is the handful that were already right
> by coincidence; nothing tells them apart from the untouched ones, so they have
> to be entered again, once.

Translations are added/updated through a **CSV round-trip** (no timeouts, easy for
a human or an AI):

1. **Download a template** for the target language — columns: `de` (source/key),
   `kind`, up to three chosen reference languages, and the target column
   (pre-filled). The file is UTF-8 (with BOM), **pipe-separated (`|`)** and every
   field is **fully quoted** (RFC 4180), so embedded `,`/`;` can never split a
   row.

   **`kind`** says what a string *is*, because the same words are translated
   differently depending on where they appear: `label` (short, sits beside a
   field), `tooltip` (a sentence), `placeholder` (a format example, usually taken
   over as it is), `speech` (read aloud — abbreviations and punctuation are
   heard, not seen) and `ui` (the editor's own chrome). A string can be several
   at once and then says so: a service name shown in a list *and* spoken in an
   announcement reads `label, speech`. Everything but `speech` derives itself
   from the Declaration the string came from; a host announces that one with
   `note_xlation_keys(*keys, kind="speech")`, since nothing else could know.
2. **Fill it offline**, then **upload** it. Rows are applied one by one
   (non-empty sets, blank clears, absent keeps; unknown keys skipped). A cell
   repeating the key is a translation like any other — that is how "take this
   one over unchanged" is said, and the only way to say it. Adding an 8th
   language prompts which existing one to replace.

   Both steps work from the same set: every key the software uses **plus** every
   key any dictionary already holds. The two differ more than one would expect —
   a string a host only registers at runtime, such as the name of a service type
   fetched from a server, is absent from the first set until something has asked
   for it. Cutting a template from the narrow set left those rows out of the
   file; uploading against it deleted their translations outright. Keys that
   really have fallen out of the software are listed under `/api/lang/info` for
   the admin, where removing them is a decision rather than a side effect.
3. A **report CSV** is returned with a per-row status and translated/total counts.

### Strings that arrive in another language

Not every display string is written by the host. A module may take them from
elsewhere — the categories of a remote catalogue, the fields of a foreign
schema — and such a string arrives in whatever language its source speaks.

Registering it as it stands would make a key in that language, which is the one
thing this library cannot represent: the completeness count would call it
translated for a language it is merely *written* in, a reader of `DECL_LANG`
would be shown a word from another language, and nothing in the template would
say which row is which. So the module settles on a `DECL_LANG` wording and notes
that as the key — and then supplies the original as a translation, because the
original is better than anything derived back out of the wording that replaced
it:

```python
config_mgr.note_xlation_keys("Companionship", "Transport services",
                             kind="speech")
config_mgr.add_original_xlations("de", {
    "Companionship":      "Begleitung",
    "Transport services": "Fahrdienste",
})
```

Two calls, because they are two things: the first decides what the software
uses, the second fills a dictionary. `add_original_xlations()` works for any
registered key, including one that came from a Declaration. The keys are now
ordinary `DECL_LANG` keys — they appear in every template, are translated like
anything else, and the German reading is there from the start.

Three rules hold, and each has a reason:

* **An existing translation is never touched.** These are starting points, not
  corrections; otherwise every restart would flatten the work of whoever
  improved on the wording the source happened to use.
* **A language nothing has a dictionary for is not created.** One would
  otherwise become a supported language on the strength of a handful of entries,
  and a host offering its users exactly the supported languages would start
  offering it.
* **Keys nobody registered are refused**, with a warning naming how many. An
  entry for a key the software does not use is an orphan the moment it is
  written, and would then be offered to a translator as work.

Settling the `DECL_LANG` wording at development time also means the set of these
keys is **fixed by the release**, not by whatever the source happens to serve
today — a module is expected to keep that mapping in a file it ships. Something
the source names later has no key, and the host needs an answer for it that does
not involve inventing one: the H4H appliance falls back to an announcement that
names no service at all.

### Keys that turn up late

`start_editor()` takes the key set as it stands, and anything registered after
that is reported once, by name:

```
Translation key 'Voice sample' appeared after the editor started; it was in no
template cut before now.
```

Which is the whole problem in one line. A key that only exists once something
has been rendered was absent from every template downloaded before that, and
from the count that told somebody their languages were complete — so a set of
translations goes out believing itself finished, and the gap shows up on a
device.

Reported rather than refused: a string that first exists when a provider runs is
legitimate, and a host cannot always know it earlier. But whoever builds a
release image should be able to see that the key set is not the one they froze,
and on a host that declares everything up front the line never appears at all.

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
| `GET /api/lang/template?lang=&refs=` | Download a translation template (admin): the protected languages, `kind`, chosen references, then the target column. |
| `POST /api/lang/upload` | Upload a filled translation CSV (admin); returns the report, or `409` asking which language to replace. |
| `GET /api/config/enum-options?path=[&arg=]` | Resolve a dynamic enum's options; `arg` is the JSON-encoded value of the `values_for` sibling. |
| `GET /api/value/capture?path=` | Long-poll (≤ 30 s) for a backend-captured value. |
| `POST /api/config/test` | Run the `test_func` for `{path, value}`. |
| `POST /api/config/probe` | Verify `{path, value}` on the device; only for `path`/`pingable` params. |
| `POST /api/session/takeover` | Take the editing session from its holder, on proof of `ui_passwd`. |
| `POST /api/end_session` | Release the editing token. |

---

## Advanced features

- **Dynamic enums** — `values` may be a function name (in `func_dict`); the editor
  fetches options via `/api/config/enum-options` when the group is expanded. The
  function returns the options dict or an error string that blocks expansion.
  Options are re-fetched after every save, since a provider computes them from a
  device state that has just changed.

  **`values_for`** names a sibling whose value the options are computed *for*.
  Its current value — the one being edited, not the one last saved — is passed to
  the provider, and the editor re-asks as soon as it changes:

  ```python
  "language": {"type": "enum", "values": "get_language_list"},
  "voice":    {"type": "enum", "values": "get_voice_list",
               "values_for": "language"},

  def get_voice_list(language):     # None while the sibling is unset
      ...
  ```

  So a pair that belongs together is chosen in either order and saved **once**.
  Without it the second field answers the question of before: you would save the
  language, reload, and only then see the voices that speak it.

  It is not a condition — no operator, no value — and it is not `relevance`,
  which decides whether a field is on screen at all. A field may carry both,
  naming different siblings. `register_params` refuses at startup if the named
  sibling is not in the same dict, if it is the field itself, if the field is not
  a dynamic enum, or if the provider does not take an argument.
- **Backend-captured values** — a `backend_provided` field shows an
  `acquire_button`; pressing it long-polls `/api/value/capture`. A module delivers
  the value with `config_mgr.handle_value_event(value, alt_target_paths)` (use
  `*` in a path to target a list member); unmatched events are no-ops. The call
  returns `True` when a waiting editor took the value — a module can use that to
  suppress whatever the captured event would otherwise trigger. While a capture
  is pending the editor freezes behind a modal overlay, so at most one capture is
  ever outstanding.
- **List uniqueness** — simple-value lists forbid duplicates; `list_keys` declares
  uniqueness for record lists, and the editor hides already-used enum options. A
  member repeating another on a declared group is dropped and reported, and the
  editor marks the colliding field and disables *Apply*: hiding taken options
  works for an enum and for nothing else, so a typed or captured value — an RFID
  arrives from the reader — had nothing standing in its way.
- **Distinctness across paths** — `distinct_values` on a named *dict* type names
  groups of paths beneath it whose values must never coincide. Paths may contain
  `*`, so a group can span a list:

  ```python
  "card_uids": {
      "distinct_values": [["abort_card_uid", "reboot_card_uid",
                         "h4h_sr_cards.*.rfid"]],
      …
  }
  ```

  Declared **once, on the container** — not as a condition repeated on each
  participant, which would state one rule three times and let the copies drift.
  It also couldn't work: a condition reaches siblings at the same level, and a
  list member cannot see past its own list. An unset value collides with nothing;
  a colliding write is refused and reported, leaving the previous value. For a
  `backend_provided` participant the check runs at **capture** — the only moment
  a value ever arrives, and so the only moment anyone can be told.
- **Testable parameters** — `test_func` + `test_func_msg` add a Test button and a
  confirmation modal, executed via `/api/config/test`.

  *Test* and *Check* are two different buttons, and the difference is who is
  responsible. **Test is declared**: only the host knows that a voice can be
  heard or a number dialled, so without `test_func` there is no button, and
  pressing it *does* something — it speaks, it rings, it lights up. **Check is
  not declared.** It belongs to validation, which is the editor's own work, and
  it appears by itself wherever validation cannot be finished in the browser.
- **Backend-verified values** — every field is checked, but most of them in the
  browser, against what the declaration says: a range, a pattern, a set of
  options, a uniqueness group. None of that needs a round trip and none of it
  needs a button.

  A `pingable` or `path` field is the exception: it is checked on the **device**,
  because only the device can answer. The file system is its own, and what
  matters about a host is whether *it* reaches it — the browser may be on the
  other interface. So the check becomes a request, and a request has a moment.

  **Leaving the field is that moment.** The value commits on `change` — blur, or
  Enter, which the editor turns into a blur — and the probe goes out with it. No
  button is needed for the ordinary case, and there is none in the sense of "press
  this to validate".

  *Check* is there for the two cases losing focus cannot cover:

  - **The value did not change, the world did.** A host was unreachable a minute
    ago because a cable was out; it is in now. Without the button the only way to
    ask again would be to retype the value, which is asking a question by
    pretending to answer a different one.
  - **Nobody typed the value.** One loaded from the store when the editor opened,
    or a `likely_val` the editor filled in, never passed through the field's
    change event and therefore carries no verdict. After taking over a session,
    *Check* is how you find out whether what is configured is reachable **now**.

  Each verdict is three-way rather than yes/no, because "not there" carries two
  very different meanings, and they get different treatment:

  | Verdict | Meaning | Effect |
  |---------|---------|--------|
  | `reachable` / `file` / `directory` | it is there | accepted |
  | `silent` | the host resolves but does not answer | accepted, reported |
  | `creatable` | the path is absent, its parent folder is not | accepted, reported |
  | `unresolvable` | the name resolves to nothing | **field marked, save refused** |
  | `missing` | not even the parent folder exists | **field marked, save refused** |

  The last two can only be a typo, so the field is marked exactly as one the
  browser itself rejects, and **Save** refuses the module while it stands. The
  value is *marked, not withdrawn*: what somebody typed stays on screen to be
  corrected, which is what the browser's own checks do — they simply refuse
  before the value is committed, whereas this answer arrives afterwards. It makes
  no difference whether the verdict came from typing or from pressing *Check*;
  the same verdict marks the same field, and Save is the one gate.

  The other two are legitimate states of a working device — a speakerphone can
  be switched off while it is configured, a log file is created on first use —
  and they leave no mark at all. One caveat on `unresolvable`: a name is also
  unresolvable when the device's own DNS is broken, and then a correct hostname
  blocks the save. An address gets around it.
- **Proposed values** — a `likely_val` is offered by the editor rather than by the
  backend: the field arrives pre-filled and the module counts as unsaved, so the
  admin either accepts the proposal by saving or types over it. Clearing the field
  keeps it clear; the proposal is offered once per form, not re-imposed on every
  redraw.

<a id="files"></a>

- **Files** — a `file` parameter holds the bare *name* of a file that lives in the
  directory the host names with `file_dir`. Declare `values` as well and it becomes
  an **enum you can extend by uploading**: the provider says which files may be
  chosen, `POST /api/config/file` adds another, and the parameter is set through
  the ordinary update path, so the module callback fires exactly as after any other
  change. The library never lists the directory itself — a host may keep unrelated
  files there, and only it can say which ones qualify.

  ```python
  "ring_tone": {"label": "Ring tone", "type": "file",
                "file_dir": "/etc/freeswitch/audio",
                "bound_to": r".+\.wav",          # fullmatch, not a suffix search
                "values": "get_ring_tone_list"}
  ```

  The name a browser sends is a claim, not a fact: anything containing a separator
  or `..` is **refused rather than cleaned**, because stripping the path off and
  carrying on would be equally safe but would hide that something sent it. Uploads
  are size-capped, and a file that fails validation afterwards is removed again
  unless it was already there.

<a id="hints"></a>

- **Hints** — a `hint` is a statement about the present, rendered above its field
  rather than behind a question mark, because it says something the reader needs
  *before* deciding. Literal text behaves like any other display string. Name a
  `func_dict` entry instead and it becomes dynamic: the editor fetches it from
  `/api/config/hint`, and the provider — `fn(lang) -> str` — produces the sentence
  itself.

  Dynamic is not a luxury. What invalidates a hint is often *not* a configuration
  change: a translator uploads a file, a remote server renames a category, and a
  statement declared once goes on asserting something nobody re-checked. Hence
  also the two things the editor draws beside the text: **the moment it was
  established**, and a button to establish it again. The timestamp is what keeps
  the sentence honest between refreshes — undated, it claims the present forever;
  dated, it stays true however long the page is left open.

  A generated sentence cannot itself be a translation key, so a provider formats
  its own templates and should announce them with `note_xlation_keys()` — otherwise
  they reach no translation template until someone has already seen the hint.

### Giving up a module's parameters

`discard_module()` exists for a two-stage provisioning: a value that has to be
present while a distributor prepares a device class, and must not be present on
the devices cloned from it afterwards. A provisioning key is the typical case.

Hiding the field would not do — what matters is that the value is off the card,
and only deleting the persisted data achieves that, since the declaration would
otherwise restore it at the next start. It is deliberately not the same as
registering an empty `param_dict`: an empty dict is a shape a module can arrive
at by accident, and the effect here is the loss of everything that module had
stored.

The module decides for itself, and it may do so either instead of registering or
later in the same run — whenever it can first tell. In the appliance this project
grew from, the speech module cannot tell at import time: what counts as
"complete" is a recording for every sentence the *application* would speak, and
the application registers after it. So it declares its parameters as usual, and
gives them up at the moment the application hands it the list:

```python
# in the speech module, at the moment the application registers its sentences
if not set(config_mgr.supported_languages()) - set(self.voiced_languages()):
    config_mgr.discard_module("5tts")      # …and the API key with it
```

Measured against the languages this deployment has, never against a number. The
appliance compared with a ceiling of seven once, and that was right only for a
deployment carrying exactly seven: one shipping five would have recorded all
five and kept its API key for ever, because five is less than seven.

The call returns `True` if there was anything to remove, and invalidates the
editor session, since the schema it is showing has just changed. Registering the
module again on a later run is the way back: if a recording is deleted, the next
start finds something missing and keeps the parameters.

---

## Own configuration parameters

`config_mgr` registers a hidden `config` module for its own state:

| Path | Meaning |
|------|---------|
| `config.ui_passwd` | admin password (factory default until changed) |

Everything else is a **deploy-time** setting, read from the environment rather
than the cvv tree: `GPSMCPMMS_CVV_DIR` and `GPSMCPMMS_UI_DIR` (working dirs,
defaults under `~/.config/gpsmcpmms/`), `GPSMCPMMS_UI_PORT` (editor port,
default 8080) and `GPSMCPMMS_SESSION_TIMEOUT` (session inactivity minutes,
default 30).

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

What this was built for is **commissioning**: taking an appliance from a bare
image to a device that is provisioned, tested and personalised for one customer —
and doing it in a single pass, standing at the device, through a browser. Every
part of that pass comes out of the same declarations: the validation, the editor
that collects the values, the verification against the real hardware, the test
buttons that prove it works, and the language the device will speak to the person
using it. No build step, no service to run, no separate string table, and no user
interface to write.

Python has plenty of configuration tooling, but it is fragmented, and none of it
covers that arc — framework-agnostic self-registration **plus** an auto-generated
web editor **plus** validation, persistence and i18n in one box. It splits roughly
into three camps:

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

### Commissioning in one pass

What a distributor actually does at the device, and what carries it:

| Step | What does the work |
|------|--------------------|
| Lock what the customer may not change, leave the rest open | `protected` + the admin password; `fixed_val` and `init_only` for what is settled once |
| Type addresses, keys and credentials | the declared types, `bound_to` patterns, `password` masking |
| Confirm that a host and a folder really exist **on the device** | the `pingable` / `path` verification, which refuses a typo at Save |
| Read a value off the hardware instead of typing it | `backend_provided` + `acquire_button`, long-polled from the reader |
| Offer only the choices that exist right now | dynamic enums, and `values_for` for a pair that depends on itself |
| Prove it works before leaving | `test_func` buttons — hear the ring tone, call the number, watch the LED |
| Hand the device over in the customer's language | every display string is already a translation key; the CSV round-trip fills seven languages |
| Take the provisioning secrets off the card | `discard_module()` |

None of that is a separate mechanism bolted on: it is one declaration per
parameter, read by the backend for validation and by the editor for the form. The
same label that appears beside a field is the key its translation is stored
under, so a device that speaks Turkish needs no string table in the application —
and in the appliance this grew from, the sentences the device *says out loud* go
through exactly that path too.

The catch is real and worth stating: the application has to be written to declare
these things rather than hardcode them. A module that validates its own input, or
builds its own screen, or keeps its own texts, gets none of it. The reward for
declaring instead is that the whole commissioning pass — and every language of it
— falls out of what you already had to write down.

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
- **Maturity** — purpose-built rather than battle-tested: no security process and
  no community behind it. What it *has* been through is one real appliance, whose
  every parameter, hardware capture, test button and spoken announcement in seven
  languages runs through it — which is evidence of fitness, not of hardening.

### When to use something else

| Need | Better fit |
|------|-----------|
| Typed application settings | `pydantic-settings` |
| Layered / multi-source config | `dynaconf`, `hydra` |
| Flat runtime settings inside a Django app | Django Constance |
| Distributed / fleet config, feature flags | Consul / etcd, Unleash / Flagsmith |
| A schema-driven form without a custom DSL | JSON Schema + RJSF |

But for the job at the top of this section — **commissioning an offline appliance:
provisioning it, verifying it against its own hardware, testing it and handing it
over personalised and in the customer's language, in one pass at the device** —
picking from that table means assembling four or five of them and writing the
editor yourself. There is no drop-in open-source equivalent; Home Assistant's
config flows come closest in spirit and are not extractable as a library.

---

## License

Licensed under the Apache License, Version 2.0 — see [LICENSE](LICENSE) (attribution in [NOTICE](NOTICE)).

Copyright 2026 saiedt
