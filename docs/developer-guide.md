# Building an application on gpsmcpmms

This is the guide for the people who write the application, not for the people
who translate it (see the [translation guide](translation-guide.en.md)) and not
for the people who commission a device.

Everything here is something this project got wrong first. The appliance it grew
from — an accessible speakerphone that files help requests, seven languages,
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

### Register every display string at startup

A string becomes a translation key when something registers it. Declarations do
that when the module registers; anything else needs `note_xlation_keys()`. Do it
next to `register_params()`, for everything you know about.

The temptation is to let a string register itself the first time it is used —
`translate()` notes its key on the way through, so it works. It works and it
lies: a template downloaded before that moment does not contain the string, and
the completeness count that told somebody their languages were finished did not
count it. The gap appears on a device, in front of a user, in a language nobody
chose.

Two of these shipped here. The names of the remote service catalogue became keys
only once somebody opened the dropdown that listed them — which is why the
commissioning guide had to open with *"first, and without fail, open this field
once"*, a defect rewritten as prose and handed to a human. And the three words
that name a voice's gender were harvested only when the voice list was rendered,
so on every device, in every language, that one spot read German. The
completeness count said 198 of 198 the whole time.

`start_editor()` snapshots the key set, and anything registered afterwards is
named once in the log. Read that log during release-making; on an application
that declares everything up front it stays empty.

### Keys are `DECL_LANG`; a foreign wording is a translation

Sooner or later a module gets its display strings from somewhere else — the
categories of a remote catalogue, the fields of a foreign schema — and they
arrive in whatever language that source speaks.

Do not register them as they stand. Settle on a `DECL_LANG` wording, register
that, and hand the original over as its first translation with
`add_original_xlations()`. Registering the foreign string makes a key in a
language the rest of the tree is not written in: the completeness count calls it
translated for a language it is merely *written* in, a reader of `DECL_LANG` is
shown a word from another one, and nothing in a template says which row is which.

```python
config_mgr.note_xlation_keys(*FROZEN.values(), kind="speech")
config_mgr.add_original_xlations("de", FROZEN)   # {key: how the source said it}
```

### Freeze what the outside world names

The set of keys belongs to the release, not to whatever a third party's server
answers today. If the catalogue is the source of your keys, a category added
over there turns every device in the field incomplete — with no way back,
because a delivered device cannot translate or record anything.

The pattern that works:

- ship a curated file mapping the outside identifier to your `DECL_LANG` wording
  and the original;
- register from that file at startup, needing no network to know what has to be
  translated;
- when the source names something the file does not know, **write it to a
  separate file** and carry on. The shipped artefact stays identical on every
  device, and the note is a starting point for the next development round.
- have an answer for the unknown case that does not involve inventing a key.
  Here a service without a key is announced without its name — worse than the
  full sentence, better than silence, and never a word nobody translated.

Match on the stable identifier where you have one, and on the wording only as a
fallback. A renamed category is otherwise a category you no longer know.

### An identifier is not a display string

Dynamic enums return `{value: {"label": …}}`, and the two halves are different
kinds of thing. The **value** is persisted and compared — never translate it,
never let it drift. The **label** is shown and belongs in every template.

When the label is an identifier rather than prose — a file name, a voice name —
mark the option `verbatim`, or every look at that list drops fifty rows into the
translation templates, in every language, for ever. A tooltip beside a verbatim
label is still prose and is still collected.

The trap is an option whose value and label are the same word. Keep them apart
on purpose: `{"none": {"label": "no ring tone"}}`, never `{"Keine": {"label":
"Keine"}}`. Change the label of the second and you have changed what is stored.

### Declared values are data

`default_val`, `fixed_val` and `likely_val` are values, not display strings, and
the library does not collect them as keys. When you write tooling of your own
that walks declarations — a bulk rename, a source-language flip — draw the same
line. A default that happens to read like a label will otherwise be translated,
and what was a device setting becomes a word.

### Measure against what the deployment has

If a module decides something about itself — whether it is finished, whether it
can give up its parameters — measure against the deployment, never against a
constant.

The speech module compared its number of recorded languages with the library's
ceiling of seven:

```python
if len(self.voiced_languages()) >= config_mgr.MAX_LANGUAGES:   # wrong
    config_mgr.discard_module("5tts")
```

Correct for a device carrying exactly seven languages, and silently fatal for
every other: a deployment shipping five would have recorded all five and kept
its API key for ever, because five is less than seven — the provisioning would
never have completed. The ceiling has since been removed, and the test now asks
what it actually wants to know:

```python
if not set(config_mgr.supported_languages()) - set(self.voiced_languages()):
    config_mgr.discard_module("5tts")
```

Giving up parameters is worth knowing about in its own right: a module that has
nothing left to configure can drop its declaration *and everything stored for
it*. That is how an API key that belonged to the workshop stops travelling to
customers.

### Do not let your knowledge become the library's rule

`set_language_validator()` lets a host refuse languages it knows it cannot serve.
Use it for what you really know, and check that the question it asks is the
question being decided.

Ours asked the speech service whether it had a voice — a *speaking* question
applied to a *reading* decision. Somebody reading the editor in Italian needs no
Italian voice. Worse, the answer was useless exactly where it mattered: with the
service unreachable every language passed, and on a delivered device without a
key it is always unreachable. The concern behind it — *"somebody translates five
hundred strings and none of them can be spoken"* — was better served by a report
naming the languages that lack recordings.

### Derive artefacts from ids, and check they survive

If your application derives files from display strings — recordings, caches,
generated documents — name them after something stable and compare the *content*
before and after any change to the strings.

Here every announcement is a `.wav` beside an `.rc` holding the text it was made
from. A single character's difference makes the recording stale, and a delivered
device has no key to redo it. Both the source-language flip and the catalogue
freeze could have invalidated seventy recordings across seven languages; what
made them safe was snapshotting all seventy texts first and comparing afterwards,
not reading the diff and hoping.

### A worked case: pairing captured identifiers with a live catalogue

Most of what an editor has to do is one field at a time. The interesting part
starts where fields constrain each other, and that is worth one full example —
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
  hiding a taken option is possible when the options are known, and impossible
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

### Test the device, not the sandbox

An off-target test that builds its own empty world tests a device that does not
exist. Point it at the dictionaries and the language allow-list your image
carries. Ours seeded the library's own instead, so the announcements came out in
`DECL_LANG` — and every expectation was written to match, which made the test
agree with itself and with nothing else.

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
and an asset inside the store you are about to delete is an asset you are about
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

### Write down what a device may still change

The last thing release-making settles is what the stages after it are allowed to
touch: which parameters a distributor sets for all its devices, which belong to
a single unit, and which the end customer sees. Write that down as a table, one
row per parameter. It answers, once and for all documents, what the value store
must contain when an image changes hands — and it forces an answer to the
questions that are otherwise discovered in the field, such as who holds the
admin password of a device that has come back for service.
