# Building an application on gpsmcpmms

This is the guide for the people who write the application, not for the people
who translate it (see the [translation guide](translation-guide.en.md)) and not
for the people who commission a device.

Everything here is something this project got wrong first. The appliance it grew
from — an accessible speakerphone that files help requests, eight languages,
every sentence pre-recorded — is named where a rule needs a story to be
believable. Read the rules, not the appliance.

There are two parts, because they are two different jobs:

1. **[Writing the application](#part-1-writing-the-application)** — the decisions
   you make in the source, most of which are cheap to get right and expensive to
   discover late.
2. **[Release-making](#part-2-release-making)** — the pass at the end that turns
   a working checkout into an image somebody else can build devices from.

---

## Part 1: Writing the application

Four worked cases come first, because a shape is easier to copy than a rule is
to apply. Each is a real problem from a real device, and each is answered by a
declaration or a file rather than by code. What follows them is shorter: one
rule that holds for every module, and then a group of practices about display
strings and what becomes of them once a device speaks more than one language.

### A worked case: pairing captured identifiers with a live catalogue

Most of what an editor has to do is one field at a time. The interesting part
starts where fields constrain each other, so that is worth one full example —
because the answer is a declaration rather than code.

The task: somebody has to pair physical tokens with categories. A token's
identifier cannot be typed, it is read by hardware. The categories come from a
remote service and change without notice. Each token stands for exactly one
category and each category for exactly one token. Two other tokens have jobs of
their own, and no identifier may ever appear twice anywhere. At least two pairs
must exist before the device is ready.

```python
type_dict = {
    "token_pair": {
        "tag": {"label": "Token", "type": "string",
                "backend_provided": True, "acquire_button": "Scan token"},
        "category": {"label": "Category it stands for", "type": "enum",
                     "values": "get_categories"},
    },
    "pair_list": {
        "list_member": {"type": "token_pair"},
        "list_keys": [["tag"], ["category"]],
        "list_size": "2..",
    },
}

param_dict = {
    "tokens": {
        "distinct_values": [["cancel_tag", "restart_tag", "pairs.*.tag"]],
        "cancel_tag":  {"label": "Cancel token", "type": "string",
                        "backend_provided": True,
                        "acquire_button": "Scan token"},
        "restart_tag": {"label": "Restart token", "type": "string",
                        "backend_provided": True,
                        "acquire_button": "Scan token"},
        "pairs": {"label": "Paired tokens", "type": "pair_list"},
    },
}
```

That is the whole specification. What each line buys:

- **`backend_provided` with `acquire_button`** makes the field read-only and puts
  a button beside it. Pressing it leaves the editor waiting on that path; the
  module reads its hardware and answers with `handle_value_event()`, which
  reports whether anybody was still waiting. It works for a path inside a list
  row, and for the row being added — the one that has no ordinal yet.
- **`list_keys: [["tag"], ["category"]]`** — two separate one-column keys, which
  is what makes the pairing a bijection: no token twice, no category twice. One
  compound key `[["tag", "category"]]` would have allowed both to repeat as long
  as the combination was new.
- The same declaration drives the dropdown: **a category another row already
  uses is not offered.** Only one-column keys do this, and only for an enum —
  hiding a taken option is possible when the options are known, but impossible
  for a value that arrives from hardware. So a captured duplicate is caught the
  other way: the write is refused, the field marked, and *Apply* disabled.
- **`distinct_values` on the container** covers the rest: two ordinary fields and
  every row of the list, in one group. It is declared once, on the thing that
  contains them all, and it has to be — a relevance-style condition reaches its
  siblings, and a list member cannot see past its own list. Three copies of one
  rule would also have drifted apart at the first edit.
- For a captured participant that check runs **at capture**, which is the only
  moment that helps: telling somebody the token was already taken *after* they
  held it against the reader is a different, worse message.
- **`list_size: "2.."`** keeps `config_ready()` false until two pairs exist, so
  the device reports itself unconfigured rather than half-working.
- The enum stores the category's **id** and shows its **label**, and the label is
  a translation key like any other — unless the provider marks the option
  `verbatim`, which is for identifiers the service invented and nobody should be
  asked to translate.

No validation function, no save handler comparing fields, no code in the editor
that knows about tokens. Everything above is enforced in the backend *and*
rendered by the editor from the same declaration, which is the point: the two
cannot disagree, because there is only one statement of the rule.

#### Delivering a captured value: what goes in `alt_target_paths`

The capture above has a second half. Pressing *Scan* leaves the editor waiting;
the module then reads its hardware and hands the result over:

```python
# every path a scanned token could legitimately fill
TOKEN_PATHS = ["tokens.cancel_tag",
               "tokens.restart_tag",
               "tokens.pairs.*.tag"]

def on_token_read(self, token):
    if config_mgr.handle_value_event(token, TOKEN_PATHS):
        return              # the editor took it; it means nothing else now
    ...                     # otherwise: whatever a token normally does
```

**The list is not "where the value goes" — it is "where it could go".** The
module cannot know which field somebody has open; the editor does. So the module
names every path this kind of value may legitimately fill, and the library hands
it to whichever one is actually waiting. Exactly one can be: a capture freezes
the editor behind a modal, so there is never a second candidate.

**`*` matches exactly one path element**, which is what makes a list row
reachable — including the row that does not exist yet. Somebody adding a pair
presses *Scan* before the row has an ordinal, and the same pattern still covers
both that template and every row already there.

**Keep the list beside the declaration.** In the appliance these are the very
three paths that also form the `distinct_values` group, and that is not a
coincidence: what may hold a token is what must be unique among tokens. Written
in two places, they will disagree eventually — put them next to each other, and
say in a comment that they are the same set.

**The return value is the point of the whole call.** One reader, two meanings:
while the editor waits, a token being held against it means *configure this
field*; at any other moment the same event means *do the thing tokens do*.
Without the `if`, teaching the device a cancel token would also cancel
something.

Name the paths this kind of value can fill, and only those. Too few is the
failure that hurts — the button waits for something that was delivered to
nobody — and a path that can never wait is dead weight at best; at worst, if the
module captures more than one kind of value, an overlapping list lets the wrong
one satisfy the wrong field.

### A worked case: keys that arrive in a foreign language

The categories of the case above — the ones a token gets paired with — come
from a remote service, and that service names them in its own language. Here that is
German. The device, meanwhile, does not only show those names on screen: it
reads some of them aloud, in whichever of eight languages the person in the room
has chosen. And this library writes every key in `DECL_LANG`, which is
English.

That is the whole difficulty, and it comes in three parts:

- **The names are keys.** A German name registered as one would be a key in a
  language the rest of the tree is not written in: the completeness count would
  call it translated for a language it is merely *written* in, a reader of
  English would be shown a German word, and nothing in a template would say
  which row is which.
- **The set of keys belongs to the release**, not to what the server answers
  today. Were the catalogue the source, a category added over there would turn
  every device in the field incomplete — with no way back, because a delivered
  device can neither translate nor record anything.
- **And a category nobody has curated yet must break nothing**, because one
  arrives sooner or later.

For this the library offers two calls and no file format at all.
`note_xlation_keys()` says *these strings are keys*, and
`add_original_xlations()` says *and here is one language's rendering of them
already*. Everything between the remote service and those two calls is the
client module's own business.

What this module invented is a file that ships with the release. What it holds
is easiest seen on one entry at two moments.

**When the service first names the category**, the device writes this by itself:

```json
{ "key":      "Begleitung",
  "original": "Begleitung",
  "id":       "bbde703b-5da1-4fac-b50c-84d4558bc92a",
  "verbatim": true }
```

It has the identifier and the foreign wording and nothing else, so the foreign
wording stands in both fields — and `verbatim` says: this entry takes part in
nothing.

**At the next release**, somebody decides what the thing is called in English:

```json
{ "key":      "Companionship",
  "original": "Begleitung",
  "id":       "bbde703b-5da1-4fac-b50c-84d4558bc92a",
  "verbatim": false }
```

One field written by hand, one mark cleared. `original` did not move: it is what
the service says, not what you decided.

Four fields, and each answers one thing:

- **`key`** is *your* wording, in `DECL_LANG`. It is the translation key, and
  every dictionary translates against it. Choosing it is a human act; nothing
  derives it from anything.
- **`original`** is what the service calls the thing. It is handed over as the
  German translation of that key, so German is complete without anybody
  translating it:

  ```python
  config_mgr.note_xlation_keys(*originals, kind="speech")
  config_mgr.add_original_xlations("de", originals)   # {key: how they said it}
  ```

  `kind="speech"` because these names are read aloud, and nothing else in the
  file could tell a translator that.
- **`id`** is the service's own identifier. Match on it first and on the
  wording only as a fallback — a renamed category is otherwise a category you
  no longer know.
- **`verbatim`** marks an entry nobody has curated yet, as in the first of the
  two above. The name is borrowed from the library, which has a `verbatim` flag
  for an enum option whose label is an identifier and must not be translated
  (see [An identifier is not a display
  string](#an-identifier-is-not-a-display-string)). The two are not the same
  thing — one is a field in this module's file, the other a flag on an option —
  but an uncurated entry produces exactly such an option, which is why they
  share a word.

**A `verbatim` entry takes part in nothing.** It names the type in the editor,
so a card can still be assigned to it — and that is all. It becomes no
translation key, it carries no original reading, and it demands no recording.
The next release-making pass therefore has one file to open: give every marked
entry an English wording, clear the mark, done.

That inaction is also what makes writing into a shipped file safe. Doing so
sounds like the opposite of freezing it, and it would be, if the added entries
did anything. Because they do not, two devices of one release can hold
different files and still behave exactly alike, and nothing a server says can
make a device in the field incomplete. **That behaviour is what has to be
protected.** A file that is the same everywhere was never the goal, only one
way of reaching it.

**Mark, never delete.** A type the service stops naming is marked as no longer
offered, and a human decides at release time whether it goes. Deleting it on
the device that serves as the master would carry the deletion into every image
built from it, and a whole series would lose the name of something that may
well come back.

**And the uncurated case needs an answer that does not invent a key.** Here a
service without a key is announced without its name — worse than the full
sentence, but better than silence, and never a word nobody translated.

Two lessons are worth taking out of this one, because both cost something here
before they were understood.

**Register at startup, not on first use.** The names become keys when the file
is read, beside `register_params()` — not when somebody first opens the list
that shows them. `translate()` does note a key on its way through, so letting
them register themselves works; it works and it lies. A template cut before
that moment does not contain them, and the count that told somebody their
languages were finished had not counted them. Here it ended with a commissioning
guide that had to open with *"first, and without fail, open this field once"* —
a defect rewritten as prose and handed to a human.

**A key is not the word you were handed.** The two calls above exist to be kept
apart: one takes what you decided, the other what somebody else said. Give the
foreign word to the first, and the completeness count calls a language
translated that the strings are merely *written* in, a reader of `DECL_LANG`
meets a word from another language, and no template says which row is which.
That is why `key` and `original` are two fields and not one.

### A worked case: trying a value before committing it

Two fields where the first parameterises the second, and the second is only
worth choosing if you can hear — or see, or dial — what it does. A speech
service is the plainest example: a language, and the voices that speak it.

```python
"language": {"label": "Language", "type": "enum",
             "values": "get_languages"},
"voice":    {"label": "Voice", "type": "enum",
             "values": "get_voices", "values_for": "language",
             "test_func": try_voice,
             "test_func_msg": "The chosen voice reads this field's hint "
                              "aloud through the speaker."},
```

**`values_for`** hands the provider the sibling's *selected* value, not the
stored one, and the editor re-asks as soon as it changes. Without it the voice
list answers the question of before: you save the language, reload, and only
then see the voices that speak it. That is not merely awkward — the first save
commits a pairing nobody chose, and if saving has consequences (here: recording
every sentence of a language) they happen in an arbitrary voice before the
intended one is reachable.

**`test_func`** receives the value in the field, not the one on disk. That is
what makes "try it first" possible with no draft state in the backend and no
second round of saving: the editor posts what is on screen, the module does the
thing, and the return value is either `True` or a sentence the editor shows.

**And here is the boundary, which cost us an evening.** A test function is given
its own value and can read stored state — and nothing else. Ours read the
*stored* language:

```python
def try_voice(value):                       # wrong
    return speak(hint_text(stored_language), voice=value)
```

Somebody chose an Arabic voice, pressed Test, and heard German: the voice did
not match the stored language, so it was dropped and the service picked its own.
The button answered a question nobody asked, and said nothing about it. Worse,
the only way to make it answer correctly was to save first — which is the one
thing the button exists to avoid.

The fix was not to pass more into the test but to stop needing it. The voice's
own name carries its language, so the value that arrives with the call is
sufficient:

```python
def try_voice(value):                       # right
    language = language_of(value) or stored_language
    return speak(hint_text(language), voice=value, language=language)
```

Derive what a test needs from the value it is given, wherever the value can
carry it. Reaching for the stored state means testing a combination that exists
nowhere — not in the field, not on the device — and being told so by nothing.

Two smaller things worth copying: `test_func_msg` is shown before the test runs,
because a button that makes a device speak or place a call should say so first;
and restore whatever you touched — a test that leaves the stored voice changed
has done more than test.

### A worked case: a fixed set of records with free contents

The third shape worth showing is the one where the *set* is the software's
decision and the *contents* are somebody else's. A status indicator is the plain
example: which states exist is decided by the application — it is the thing that
switches between them — while how each one looks belongs to whoever installs the
device.

```python
type_dict = {
    "state_conf": {
        "rgb":        {"label": "Colour", "type": "color"},
        "brightness": {"label": "Brightness", "type": "float",
                       "bound_to": "0..1", "s2g_scale": "*100"},
        "animation":  {"label": "Animation", "type": "enum", "values": {
                           "none":   {"label": "None"},
                           "blink":  {"label": "Blink"},
                           "rotate": {"label": "Rotate"}},
                       "default_val": "none"},
        "on_time":    {"label": "Pulse duration (ms)", "type": "float",
                       "s2g_scale": "*1000",
                       "relevance": 'animation!="none"'},
        "off_time":   {"label": "Pause duration (ms)", "type": "float",
                       "s2g_scale": "*1000", "likely_val": 0.5,
                       "relevance": 'animation=="blink"'},
    },
    "state": {
        "id":    {"type": "string", "hidden": True, "init_only": True},
        "label": {"label": "Name", "type": "string", "init_only": True},
        "conf":  {"label": "Settings", "type": "state_conf",
                  "test_func": show_state,
                  "test_func_msg": "Shows this state now, so you can look "
                                   "at it."},
    },
    "state_list": {"list_member": {"type": "state"}, "list_size": "2.."},
}

param_dict = {
    "states": dict({"label": "Supported states", "type": "state_list"},
                   # lock the list only if we actually know its contents
                   **({"fixed_val": states} if states else {})),
}
```

- **`fixed_val` on a list locks length and composition, not the leaves inside.**
  Nobody adds a state, nobody removes one, but everybody may change how each
  looks. Without that distinction you would need a second mechanism for "editable
  within, closed without".
- **`init_only` inside an editable record** freezes the two fields that *are* the
  record's identity. Set once — here by the `fixed_val` above — and never again,
  while its siblings stay open. A record can be partly frozen.
- **`hidden`** keeps the id out of sight without keeping it out of the tree: the
  application matches on it, and nobody needs to read a slug.
- **`relevance` shapes the record from inside it.** A pulse duration matters
  only when something is animated, a pause only when it blinks, and each
  condition names its own sibling. This is not cosmetic: a field whose relevance
  is false does not need a value, so `config_ready()` does not wait for a pause
  duration on a state that never blinks — which is the difference between a
  device that reports itself ready and one that never does.
- **`test_func` sits on the dict, not on a leaf.** A colour on its own cannot be
  judged; the thing to look at is the whole combination, lit. Put the button
  where the answer is.
- **`s2g_scale`** lets storage and display disagree on purpose — seconds on the
  device, milliseconds on the screen; a fraction in the tree, a percentage in
  front of a person.

The last line of the `param_dict` is the one to copy, though. `fixed_val` is
written **only if the states are known** — a module registering on its own,
before the application has told it anything, must not freeze a list whose
contents it is guessing. Lock what you know; a lock set on an assumption is
worse than no lock, because the assumption is now permanent.

### Your device is not the deployment

A module that decides something about itself — whether it can render what it was
asked to, whether it is finished, whether it may give up its parameters — has to
measure against the values *this* deployment declared. Never against a literal,
and never against what happens to be on the desk.

The status display is the plain case. Its declaration says the number of lamps
is a deployment's decision, and says the range:

```python
"num_leds": {"label": "Number of LEDs", "type": "int",
             "bound_to": "24..1000", "default_val": 24},
```

Twenty-four is the ring most devices carry, and it is the default — so a module
written on such a device works, and keeps working for as long as nobody tries
anything else:

```python
for i in range(24):                       # wrong
    self.pixels[i] = colour
```

On a device with a three-hundred-lamp strip the same line lights the first
twenty-four and leaves the rest dark. Nothing raises and nothing is logged; the
strip looks broken rather than misconfigured, which sends whoever installed it
looking for a loose connector. The declaration had already said the number was
not the code's to know:

```python
for i in range(self.num_leds):            # right
    self.pixels[i] = colour
```

The larger decision works the same way. When a module asks whether it is
finished, it should ask what is still unset — `config_ready()` takes a path, so
a module can ask about its own subtree — rather than count what it has done and
compare the count with a number it chose itself. A count is right for exactly
one deployment: the one the author had in front of them.

Being finished is worth knowing about in its own right, because a module that
has nothing left to configure can drop its declaration *and everything stored
for it* with `discard_module()`. That is how an API key belonging to the
workshop stops travelling to customers.

### Tips and tricks for multi-linguality

These all come from the same place: a display string is not an identifier, and
a completeness count is only as honest as the moment it was taken. Each is a
single decision: cheap to get right in the source, but expensive to discover on
a device somebody has already been given.

#### Register every display string at startup

A string becomes a translation key when something registers it. Declarations do
that when the module registers; anything else needs `note_xlation_keys()`. Do it
next to `register_params()`, for everything you know about.

The temptation is to let a string register itself the first time it is used —
`translate()` notes its key on the way through, so it works. It works, but it
lies: a template downloaded before that moment does not contain the string, and
the completeness count that told somebody their languages were finished did not
count it. The gap appears on a device, in front of a user, in a language nobody
chose.

Two of these shipped here. One was the remote service catalogue, told in the
worked case above. The other: the three words that name a voice's gender were
harvested only when the voice list was rendered, so on every device, in every
language, that one spot read German. The completeness count said 198 of 198 the
whole time.

`start_editor()` snapshots the key set, so anything registered after that is
named once in the log. Read that log during release-making; on an application
that declares everything up front it stays empty.

#### An identifier is not a display string

Dynamic enums return `{value: {"label": …}}`. The two halves look alike, but
they are different kinds of thing. The **value** is persisted and compared — never translate it,
never let it drift. The **label** is shown and belongs in every template.

When the label is an identifier rather than prose — a file name, a voice name,
or the wording of a category nobody has curated yet — mark the option
`verbatim`, or every look at that list drops fifty rows into the translation
templates, in every language, for ever. A tooltip beside a verbatim label is
still prose and is still collected. The fourth worked case above turns that
mark into a workflow.

The trap is an option whose value and label are the same word. Keep them apart
on purpose: `{"none": {"label": "no ring tone"}}`, never `{"Keine": {"label":
"Keine"}}`. If you change the label of the second, you have changed what is stored.

#### Declared values are data

`default_val`, `fixed_val` and `likely_val` are values, not display strings, so
the library does not collect them as keys. When you write tooling of your own
that walks declarations — a bulk rename, a source-language flip — draw the same
line. Otherwise a default that happens to read like a label will be translated,
and a device setting has turned into a word.

#### Do not let your knowledge become the library's rule

`set_language_validator()` lets a host refuse languages it knows it cannot serve.
Use it for what you really know, and check that the question it asks is the
question being decided.

Ours asked the speech service whether it had a voice — a *speaking* question
applied to a *reading* decision. Somebody reading the editor in Italian needs no
Italian voice. Worse, the answer was useless exactly where it mattered: with the
service unreachable, every language passed — and on a delivered device without
a key, it is always unreachable. The concern behind it — *"somebody translates
five hundred strings that the device cannot speak"* — was better served by a report
naming the languages that lack recordings.

#### Derive artefacts from ids, and check they survive

If your application derives files from display strings — recordings, caches,
generated documents — name them after something stable and compare the *content*
before and after any change to the strings.

Here every announcement is a `.wav` beside an `.rc` holding the text it was made
from. A single character's difference makes the recording stale. A delivered
device has no key to make it again. Both the source-language flip and the catalogue
freeze could have invalidated seventy recordings across seven languages; what
made them safe was snapshotting all seventy texts first and comparing afterwards,
not reading the diff and hoping.

#### Test the device, not the sandbox

An off-target test that builds its own empty world tests a device that does not
exist. Point it at the dictionaries and the language allow-list your image
carries. Ours seeded the library's own instead, so the announcements came out in
`DECL_LANG`. Every expectation was then written to match, so the test agreed
with itself and with nothing else.

---

## Part 2: Release-making

Release-making is a pass of its own, not the last hour of development. It turns
a checkout into something a distributor can build devices from, and most of what
it settles cannot be settled later: a delivered device has no key, no catalogue
and nobody to ask.

### Translate last

Do not translate while the strings are still moving. Every rewording invalidates
work in every language, and a half-translated set is indistinguishable from a
finished one from the inside.

Cut the templates when the string set has stopped changing — which is a thing you
can check rather than feel: start the editor, exercise the application, and read
the log for keys that turned up late. An application that declares everything up
front produces none.

The log answers the other direction too. Building a template names the keys that
no registration touched in this run: strings some dictionary still translates
while nothing uses them. A few of those are only waiting for a code path that has
not run yet; the rest are the leftovers of a rewording, and they are worth
settling before a language is called finished.

### Translate fully, then record

If your application speaks, reads aloud or otherwise renders text into a fixed
artefact, complete the translation of a language *before* generating anything
from it. An untranslated string falls back to its key, and the fallback is
readable — but a voice reading English sentences with a Turkish accent is not a
gap somebody notices in review; it is a gap somebody notices in a living room.

The completeness gate belongs at the moment of generating, not at the moment of
release. A language that only lives in the editor may lag: whoever sees an
untranslated label is an administrator, and can cope.

### Clean the value store

Delete the configuration store before imaging. Defaults belong in declarations,
where a developer has `default_val`, `likely_val` and `fixed_val` to say what a
fresh device should start with; what accumulates in the store during development
is one machine's state, including whatever secrets were typed into it.

Watch where `file` parameters put their uploads — `file_dir` is yours to choose,
so an asset inside the store you are about to delete is an asset you are about
to delete.

### Keep the assets out of the secret store

Whatever the release carries — dictionaries, the language allow-list — must live
where it can be versioned. Whatever belongs to one machine — keys, passwords —
must live where it can never be. `GPSMCPMMS_UI_DIR` and `GPSMCPMMS_CVV_DIR` are
separate for exactly this reason.

Ours put both under one directory, so the whole tree had to be excluded from
version control, and the translations had nowhere to live but the device and —
by a route nobody planned — this library's own package. Which is how a
customer's service catalogue came to ship as the default kit of a public
library.

### Ship your own dictionaries, and gate them

The dictionaries your image carries are a release artefact: produced once,
reviewed like source, and versioned with the code they belong to. Gate them the
way this library gates its own — **complete**, so no language is short of a
string, and **nothing foreign**, so nothing leaks in from elsewhere. The second
half is the one that has to be learnt; it is the check that would have caught
the leak above on the day it happened.

Note that `DECL_LANG` needs no dictionary at all. The keys are already written
in it, and a file repeating each of them after itself is ballast that every
change has to maintain twice.

### Bump the version

`pip install git+https://…` compares the *version*, not the commit. With an
unchanged number it clones, reads the metadata, and quietly does nothing —
leaving the old code installed and no error to notice. This costs an afternoon
exactly once per person.

### Think twice before narrowing a Declaration

A release carries the Declarations, and those decide what the values already on
a device are still allowed to be. Tighten a `bound_to`, drop an option from a
static enum, change a type — and every stored value that no longer fits is
dropped when the device next starts. The paths are named in the log, and the
parameter goes back to being unset.

Nothing converts it. The value is dropped while the module's state is loaded,
before any code of yours has seen it, so there is nowhere to put a migration
even if you wanted one.

What follows is by design and worth picturing. `config_ready()` turns false, and
a host that acts on it says so — the appliance this guide comes from falls back
to a configuration state and changes the colour it shows. The device does not
quietly run on a wrong value; it stops and asks. That is why no migration
mechanism is missing here.

The cost of asking, though, is not the same everywhere:

- An **unprotected** value costs its owner a minute. They are standing at the
  editor anyway.
- A **protected** one costs a visit. It needs the admin password and the
  knowledge of whoever provisions devices, multiplied by every device the release
  reaches.

So treat the two asymmetrically. Widening a Declaration is free, because every
stored value still fits. Narrowing one on an unprotected parameter is a nuisance
worth a line in the release notes. Narrowing one on a protected parameter is a
re-provisioning campaign and should be decided as one — or avoided by leaving
the Declaration wide and correcting the value where the module receives it.

### Write down what a device may still change

The last thing release-making settles is what the stages after it are allowed to
touch: which parameters a distributor sets for all its devices, which belong to
a single unit, and which the end customer sees. Write that down as a table, one
row per parameter. It answers, once and for all documents, what the value store
must contain when an image changes hands — and it forces an answer to the
questions that are otherwise discovered in the field, such as who holds the
admin password of a device that has come back for service.
