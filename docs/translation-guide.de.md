# Hub4Help Konfigurationseditor — Anleitung zu Übersetzungen

Diese Anleitung erklärt, wie Sie eine **neue Sprache hinzufügen** oder eine
**bestehende Übersetzung aktualisieren**. Das eigentliche Übersetzen geschieht
offline in einer kleinen Datei — durch Sie selbst oder mit Hilfe eines
KI-Assistenten. So können Sie sich beliebig viel Zeit lassen und jederzeit
später weitermachen.

---

## Bevor Sie beginnen

- Sie benötigen das **Administrator-Passwort** (das bei der Inbetriebnahme des
  Geräts festgelegt wurde).
- Es kann immer nur ein Administrator gleichzeitig bearbeiten.
- Der Editor startet auf Deutsch. Über die Sprachauswahl (**Sprache**) in der
  obersten Zeile können Sie jederzeit eine andere Sprache wählen.

---

## Schritt 1 — Administrator-Modus freischalten

1. Klicken Sie in der obersten Zeile auf **Geschützte Parameter anzeigen**.
2. Geben Sie das Administrator-Passwort ein.

Nun erscheint die Schaltfläche **Übersetzungen verwalten**.

---

## Schritt 2 — Vorlage herunterladen

1. Klicken Sie auf **Übersetzungen verwalten**.
2. Wählen Sie unter **Zielsprache** entweder eine bestehende Sprache aus, oder
   wählen Sie **Neuer Sprachcode** und geben Sie einen 2–3 Buchstaben langen
   Code ein, z. B. `fr`, `it` oder `es`.
3. Setzen Sie unter **Referenzsprachen (max. 3)** bis zu drei Häkchen bei
   bestehenden Sprachen. Diese werden als zusätzliche Hilfsspalten aufgenommen
   und geben einem menschlichen Übersetzer — oder einer KI — nützlichen Kontext.
4. Klicken Sie auf **Vorlage herunterladen**. Eine Datei namens `<code>.csv`
   (z. B. `fr.csv`) wird auf Ihrem Rechner gespeichert.

Die Datei ist eine UTF-8-Textdatei. Ihre Spalten sind:

| Spalte          | Bedeutung                                                              |
|-----------------|-----------------------------------------------------------------------|
| `de`            | Der deutsche Quelltext — zugleich der Schlüssel. **Nicht verändern.**  |
| Referenz(en)    | Bestehende Übersetzungen, nur zur Ansicht. **Nicht verändern.**        |
| `<code>` (letzte) | Die Zielsprache — **diese Spalte füllen Sie aus.**                  |

Die Felder sind durch einen senkrechten Strich `|` getrennt, und jedes Feld ist
in doppelte Anführungszeichen eingeschlossen (damit Kommas und Semikolons
innerhalb eines Textes eine Zeile niemals zerreißen können).

---

## Schritt 3 — Übersetzungen eintragen

- Bearbeiten Sie **nur die letzte Spalte** (Ihre Zielsprache). Lassen Sie die
  deutsche Spalte und die Referenzspalten unverändert — sie sind die Schlüssel
  und der Kontext.
- Ein **leeres** Feld bedeutet „noch nicht übersetzt“; dieser Eintrag erscheint
  dann einfach auf Deutsch. Sie dürfen einige Einträge jetzt und den Rest später
  übersetzen.
- Sie können von Hand übersetzen oder die gesamte Datei einem KI-Assistenten
  übergeben (z. B. *„Bitte fülle die letzte Spalte mit der französischen
  Übersetzung“*). Der deutsche Quelltext und die Referenzspalten liefern alles
  Nötige.

### Bearbeiten in Microsoft Excel (bitte lesen)

Deutsches Excel erfordert eine bestimmte Vorgehensweise — **öffnen Sie die Datei
nicht per Doppelklick**.

**a) Datei importieren**

1. Öffnen Sie Excel mit einer **leeren** Arbeitsmappe.
2. Wählen Sie **Daten ▸ Aus Text/CSV** (bzw. „Aus Text“) und wählen Sie Ihre
   `<code>.csv` aus.
3. Stellen Sie im Dialog ein:
   - **Trennzeichen = senkrechter Strich `|`**
   - **Texterkennungszeichen = `"` (doppeltes Anführungszeichen)**
   - **Datentyp der Spalten = Text** für *jede* Spalte, dann laden.

**b) Tabelle in einen normalen Bereich umwandeln**

Excel importiert die Daten als *formatierte Tabelle* (mit Filterpfeilen und
Färbung). Wandeln Sie diese zuerst in einen normalen Bereich um: Klicken Sie in
eine beliebige Zelle der Daten, öffnen Sie die Registerkarte
**Tabellenentwurf** und klicken Sie auf **In Bereich konvertieren**; bestätigen
Sie.

**c) Lange Texte lesbar machen**

Markieren Sie das gesamte Tabellenblatt — klicken Sie auf das kleine Feld oben
links (über Zeile 1, links von Spalte A) oder drücken Sie **Strg+A** — und
klicken Sie auf **Start ▸ Zeilenumbruch**. Die langen Tooltips werden nun
innerhalb ihrer Zellen umgebrochen, sodass Sie sie lesen und bearbeiten können.

**d) Nur die letzte Spalte bearbeiten** (Ihre Zielsprache).

**e) Im Pipe-Format zurückspeichern**

Excel kann eine Datei nicht mit `|` als Trennzeichen speichern. Erzeugen Sie die
Zeilen daher mit einer kleinen Hilfsformel:

1. Geben Sie in der ersten freien Spalte eine Formel ein, die jede Spalte in
   Anführungszeichen setzt und die Spalten mit `|` verbindet. Für eine Datei mit
   den drei Spalten A, B, C (`de`, eine Referenz, Zielsprache) gehen Sie in die
   Zelle **E1** und geben ein:
   ```
   ="""" & A1 & """|""" & B1 & """|""" & C1 & """"
   ```
   Passen Sie die Formel an, falls Ihre Datei eine andere Spaltenzahl hat
   (z. B. keine Referenzspalte oder bis zu drei davon).
2. Kopieren Sie diese Zelle über **alle Zeilen** nach unten. Die Spalte enthält
   nun jede Zeile genau im vom Editor erwarteten Format: `"…"|"…"|"…"`.
3. Markieren Sie die gesamte Hilfsspalte und drücken Sie **Strg+C**.
4. Öffnen Sie die ursprünglich heruntergeladene `<code>.csv` im **Editor
   (Notepad)**, drücken Sie **Strg+A**, dann **Strg+V**, dann **Strg+S**. Die
   Datei enthält nun Ihre bearbeiteten Zeilen im richtigen Format und ist bereit
   zum Hochladen. (Behalten Sie das `.csv`-Format; speichern Sie sie nie als
   `.xlsx`.)
   > Falls Umlaute oder andere Sonderzeichen danach falsch aussehen, speichern
   > Sie erneut über **Datei ▸ Speichern unter** mit der Codierung **UTF-8**.

> Einfachste Alternative: Ein einfacher Texteditor (Notepad++, VS Code) oder ein
> KI-Assistent umgeht all diese Excel-Schritte vollständig.

---

## Schritt 4 — Datei hochladen

1. Wählen Sie zurück in **Übersetzungen verwalten** neben
   **Übersetzungsdatei hochladen** Ihre ausgefüllte `<code>.csv`.
2. Klicken Sie auf **Hochladen**.
3. Ein Bericht namens `<code>.report.csv` wird automatisch heruntergeladen, und
   eine kurze Meldung zeigt, wie viele Einträge übersetzt wurden
   (z. B. *„37 / 152 übersetzt“*).

Behalten Sie den Dateinamen `<code>.csv` bei, damit der Editor die Zielsprache
erkennt; andernfalls werden Sie nach dem Code gefragt. Die Datei muss eine
**echte CSV-Datei (Text)** sein — eine Excel-Arbeitsmappe **`.xlsx`** wird mit
einer klaren Meldung abgelehnt. Laden Sie also stets die `.csv` hoch.

---

## Schritt 5 — Bericht lesen

Die **Status**-Spalte des Berichts bedeutet:

| Status                                | Bedeutung                                                        |
|---------------------------------------|------------------------------------------------------------------|
| `übernommen`                          | Ihre Übersetzung wurde übernommen                                |
| `keine Übersetzung`                   | das Feld wurde leer gelassen                                     |
| `nicht in Datei`                      | die Zeile war nicht in Ihrer Datei; der bisherige Wert bleibt    |
| `übersprungen: unbekannter Schlüssel` | dieser deutsche Schlüssel wird nicht mehr verwendet und wurde übergangen |

Wechseln Sie die Sprachauswahl auf Ihren Zielcode, um das Ergebnis direkt im
Editor zu sehen.

---

## Gut zu wissen

- Es können **bis zu sieben Sprachen** gleichzeitig bestehen. Fügen Sie eine
  achte hinzu, fragt der Editor, welche bestehende Sprache entfernt werden soll
  (Deutsch kann nie entfernt werden).
- **Deutsch (`de`) ist die Quelle** und kann hier weder bearbeitet noch entfernt
  werden — es kommt aus der Software selbst.
- Übersetzungen dürfen **unvollständig** bleiben: alles Nichtübersetzte wird auf
  Deutsch angezeigt, und ein erneutes Herunterladen der Vorlage zeigt Ihren
  gespeicherten Fortschritt, sodass Sie jederzeit weitermachen können.
- Klicken Sie am Ende auf **Sitzung beenden**, damit ein anderer Administrator
  bearbeiten kann.
