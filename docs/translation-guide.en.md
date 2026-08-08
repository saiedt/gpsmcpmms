# Hub4Help Configuration Editor — Translation Guide

This guide explains how to **add a new interface language** or **update an
existing translation**. The actual translating happens offline in a small file
— done by you or with the help of an AI assistant — so you can take as much time
as you need and continue later at any point.

---

## Before you start

- You need the **administrator password** (the one set when the device was
  provisioned).
- Only one administrator can edit at a time.
- To read the editor itself in English, choose **en** in the language selector
  (**Sprache / Language**) in the top row. The button names below then appear in
  English; their German originals are given in brackets, because a new device
  starts in German.

---

## Step 1 — Unlock administrator mode

1. In the top row, click **Show protected parameters**
   *(Geschützte Parameter anzeigen)*.
2. Enter the administrator password.

A **Manage translations** *(Übersetzungen verwalten)* button now appears.

---

## Step 2 — Download a template

1. Click **Manage translations**.
2. Under **Target language** *(Zielsprache)*, either pick an existing language,
   or choose **New language code** *(Neuer Sprachcode)* and type a 2–3 letter
   code such as `fr`, `it` or `es`.
3. Under **Reference languages (max. 3)** *(Referenzsprachen (max. 3))*, tick up
   to three existing languages to include as helper columns. They give a human
   translator — or an AI assistant — extra context.
4. Click **Download template** *(Vorlage herunterladen)*. A file named
   `<code>.csv` (for example `fr.csv`) is saved to your computer.

The file is a UTF-8 text file. Its columns are:

| Column        | Meaning                                                          |
|---------------|------------------------------------------------------------------|
| `key`         | The source text — this is also the key. **Do not change it.**     |
| `src`         | Which language that key is written in. **Do not change it.**      |
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

- Edit **only the last column** (your target language). Leave the German and
  reference columns exactly as they are — they are the keys and the context.
- A **blank** cell means "not translated yet"; that entry will simply show the
  German text, and the language counts as incomplete until it is filled. You may
  translate some entries now and the rest later.
- When an entry is to be **taken over unchanged**, **repeat the German text** in
  your column. Leaving it blank will not do: blank means "still missing",
  repeated means "I looked at this, and it stays". It comes up more often than
  you would think — a word that reads the same in your language ("OK"), and
  fields that are not a sentence at all, such as the format example
  `004961501834300` for a phone number.
- You can translate by hand, or hand the whole file to an AI assistant
  (e.g. *"please fill the last column with the French translation"*). The German
  source and the reference columns give it everything it needs.

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

1. Back in **Manage translations**, next to **Upload translation file**
   *(Übersetzungsdatei hochladen)*, choose your filled `<code>.csv`.
2. Click **Upload** *(Hochladen)*.
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
  asks which existing language to remove (German can never be removed).
- **German (`de`) is the source** and cannot be edited or removed here — it
  comes from the software itself.
- Translations may stay **partial**: anything untranslated is shown in German,
  and re-downloading the template shows your saved progress, so you can always
  continue later.
- When you are finished, click **End session** *(Sitzung beenden)* so that
  another administrator can edit.
