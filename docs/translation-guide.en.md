# Translation Guide

This guide explains how to **add a new interface language** or **update an
existing translation**. The actual translating happens offline in a small file
— done by you or with the help of an AI assistant — so you can take as much time
as you need and continue later at any point.

---

## Before you start

- You need the **administrator password** (the one set when the device was
  provisioned).
- Only one administrator can edit at a time.
- The editor opens in your browser's language if a translation for it exists, and
  in English otherwise. **Language** in the top row switches it at any time; the
  button names below are the English ones.

---

## Step 1 — Unlock administrator mode

1. In the top row, click **Show protected parameters**.
2. Enter the administrator password.

Two buttons now appear: **Add new translation** and **Edit existing
translation**.

---

## Step 2 — Download a template

1. Click **Add new translation** for a language the device does not have yet, or
   **Edit existing translation** to improve one it does. (The second is disabled
   while there is nothing to edit, and says so: *No translation exists yet*.)
2. For a new language, type a 2–3 letter **Language code** such as `fr`, `it` or
   `es`, and the **Language name** as speakers of it write it — `Français`, not
   `French`. That name is what every language menu will show.

   Both fields accept typing only where the device leaves the choice of language
   open. Where the application ships a fixed list of permitted languages, pick
   one from the menu in front of them instead; the two fields then only show the
   code and the name of what you picked.
3. On the next row, tick up to three existing languages as helper columns:
   *Translating the source keys, with up to 3 languages as further context*. They
   give a human translator — or an AI assistant — something to compare against.
4. Click **Download CSV**. A file named `<code>.csv` (for example `fr.csv`) is
   saved to your computer.

The file is a UTF-8 text file. Its columns are:

| Column        | Meaning                                                          |
|---------------|------------------------------------------------------------------|
| `en` (first)  | The text to translate, as the software writes it. **Do not change it.** |
| `kind`        | What the text is and where it appears (see below). **Do not change it.** |
| reference(s)  | Existing translations, shown only for reference. **Do not change them.** |
| `<code>` (last) | The target language — **this is the column you fill in.**       |

The `kind` column tells you what matters about a row. A text can be several
things at once, and then both are named, e.g. `label, speech`.

| `kind`        | What it means for your translation                                |
|---------------|-------------------------------------------------------------------|
| `label`       | A caption beside a field or on a button — **keep it short**, or the layout wraps. |
| `tooltip`     | Explanatory text behind the question mark — room for a full sentence. |
| `placeholder` | A format example inside an input, such as a phone number. Usually **taken over unchanged** (see below). |
| `speech`      | **Read aloud** by the device. Abbreviations, brackets and symbols are spoken as they stand; write it the way you would say it. A colon produces a short pause, a line break a full second. |
| `ui`          | The editor's own interface — buttons, messages, headings.         |

Fields are separated by a vertical bar `|`, and every field is wrapped in
double quotes (so that commas and semicolons inside a text can never split a
row).

---

## Step 3 — Fill in the translations

- Edit **only the last column** (your target language). Leave every column to
  the left of it exactly as it is — they are the source and the context.
- A **blank** cell means "not translated yet"; that entry will show the source
  text instead, and the language counts as incomplete until it is filled. You may
  translate some entries now and the rest later.
- When an entry is to be **taken over unchanged**, **repeat the source text** in
  your column. Leaving it blank will not do: blank means "still missing",
  repeated means "I looked at this, and it stays". It comes up more often than
  you would think — a word that reads the same in your language ("OK"), and
  fields that are not a sentence at all, such as the format example
  `004961501834300` for a phone number.
- You can translate by hand, or hand the whole file to an AI assistant. The
  source text, the `kind` and the reference columns give it everything it needs.

### Handing the file to an AI assistant

Attach the downloaded `<code>.csv` and give it a prompt like the one below.
Replace `<LANGUAGE>` with the language you want and `<code>` with the column
name, and keep the rules — each one is there because leaving it out produces a
file that looks correct but breaks something.

> You are translating the interface of a configuration editor into
> **\<LANGUAGE\>**. The attached `<code>.csv` is UTF-8 text, one row per string,
> fields separated by `|`, every field wrapped in double quotes.
>
> The first column is the source text you translate. Then `kind` (what the text
> is), possibly further reference languages as context, and last the target
> column `<code>` — the only column you may write in.
>
> 1. Return the **complete** file: every row, in the same order, same format,
>    nothing added, nothing omitted, nothing summarised or abbreviated.
> 2. Fill **only the last column**. Copy every column to the left of it through
>    unchanged.
> 3. Anything in curly braces — `{n}`, `{langs}`, `{max}`, `{service}`, `{scope}`
>    — is a placeholder the software fills in at runtime. Keep each one exactly
>    as it is, including the braces and the spelling inside them. You may move it
>    within the sentence if the grammar of \<LANGUAGE\> requires it. `{scope}` is
>    filled with another row of this same file, so leave the brackets around it
>    where the source has them and do not write the words in yourself.
> 4. Respect the `kind` column:
>    - `label` — a caption beside a field or on a button: **keep it short**.
>    - `tooltip` — explanatory text: a full sentence is fine.
>    - `placeholder` — a format example, such as a phone number: repeat the
>      source text unchanged unless that format really differs in \<LANGUAGE\>.
>    - `speech` — **read aloud** by a device, to an elderly person who may be
>      asking for help. Write it the way you would say it: no abbreviations, no
>      brackets, no symbols. Keep the punctuation, because a colon becomes a
>      short pause and a line break a one-second pause. Address the listener
>      politely.
>    - `ui` — the editor's own buttons and messages, read by an administrator.
> 5. If a text is already correct as it stands in \<LANGUAGE\> — a word that is
>    the same, for instance — **repeat it** rather than leaving the cell empty.
>    An empty cell means "not translated yet".
> 6. Use the other columns for context when a text is short or ambiguous.
> 7. Use the quotation marks and punctuation conventions of \<LANGUAGE\>.
>
> Return the file first. If you had to guess anywhere, list those rows briefly
> afterwards.

Two things are worth checking on the answer before you upload it: that it has
**as many rows as the file you sent**, and that no `{…}` placeholder has been
translated or lost. The upload reports the rest — and a row it cannot use is
listed in the report rather than silently dropped.

### Editing in Microsoft Excel (please read)

German Excel needs a specific procedure — **do not double-click the file**.

**a) Import the file**

1. Open Excel with a **blank** workbook.
2. Choose **Data ▸ From Text/CSV** (or "From Text") and select your
   `<code>.csv`.
3. In the dialog set:
   - **Delimiter / separator = Vertical bar `|`**
   - **Text qualifier = `"` (double quote)**
   - **Column data type = Text** for *every* column, then load.

**b) Convert the table to a normal range**

Excel imports the data as a *formatted table* (with filter arrows and colouring).
Turn it back into a plain range first: click any cell in the data, open the
**Table Design** tab *(Tabellenentwurf)* and click **Convert to Range**
*(In Bereich konvertieren)*, then confirm.

**c) Make the long texts readable**

Select the whole sheet — click the small box at the top-left corner (above row 1,
left of column A) or press **Ctrl+A** — and click **Home ▸ Wrap Text**
*(Start ▸ Zeilenumbruch)*. The long tooltips now wrap inside their cells so you
can read and edit them.

**d) Edit only the last column** (your target language).

**e) Save back into the pipe format**

Excel cannot save a file that uses `|` as the separator, so build the lines with
a small helper formula:

1. In the first free column, enter a formula that wraps every column in quotes
   and joins them with `|`. For a file with the three columns A, B, C
   (`de`, one reference, target), go to cell **E1** and enter:
   ```
   ="""" & A1 & """|""" & B1 & """|""" & C1 & """"
   ```
   Adapt it if your file has a different number of columns (e.g. no reference
   column, or up to three of them).
2. Copy that cell down over **all rows**. The column now holds each line exactly
   as the editor expects: `"…"|"…"|"…"`.
3. Select the whole helper column and press **Ctrl+C**.
4. Open the original downloaded `<code>.csv` in **Notepad**, press **Ctrl+A**,
   then **Ctrl+V**, then **Ctrl+S**. The file now contains your edited lines in
   the correct format, ready to upload. (Keep it a `.csv`; never save it as
   `.xlsx`.)
   > If umlauts or other special characters look wrong afterwards, re-save with
   > **File ▸ Save As** and Encoding **UTF-8**.

> Simplest alternative: a plain text editor (Notepad++, VS Code) or an AI
> assistant avoids all of these Excel steps entirely.

---

## Step 4 — Upload the file

1. Back in the translation panel, the third row spells out the sequence:
   *Translation file: start by* … *then* … *finally*. Click
   **Select completed CSV** and choose your filled `<code>.csv`.
2. Click **Upload the selected CSV**.
3. A report named `<code>.report.csv` downloads automatically, and a short
   message shows how many entries were translated (e.g. *"37 / 152 translated"*).

Keep the file name as `<code>.csv`, so the editor recognizes the target
language; otherwise it will ask you for the code. The file must be a **real CSV
(text)** — an Excel **`.xlsx`** workbook is rejected with a clear message, so
always upload the `.csv`.

---

## Step 5 — Read the report

The report's **status** column means:

| Status                 | Meaning                                                        |
|------------------------|----------------------------------------------------------------|
| `applied`              | your translation was applied                                   |
| `no translation`       | the cell was left blank                                        |
| `unchanged`            | the row was not in your file; the previous value was kept      |
| `not in file`          | the row was not in your file and had no translation before     |
| `skipped: unknown key` | that key is no longer in use and was ignored                   |

Switch the language selector to your target code to see the result live in the
editor.

---

## Good to know

- **Up to seven languages** can exist at once. If you add an eighth, the editor
  asks which existing language to remove. **English** and **German** cannot be
  removed: English is what the keys are written in, German is what this project
  ships for.
- A language needs no translation of the keys already written in it — they count
  as done. That is why a device whose application is written in German reports
  German as complete without anyone translating its labels into German.
- Translations may stay **partial**: anything untranslated shows its source
  text, and re-downloading the template shows your saved progress, so you can
  always continue later.
- Sometimes you will find **one row where you might expect two**. If the
  application writes a label that is word for word what the editor's own text
  already says in that language, the two are one entry: you translate it once,
  and both use your wording. The `kind` column then lists both uses.
- When you are finished, click **End session** so that another administrator
  can edit.
