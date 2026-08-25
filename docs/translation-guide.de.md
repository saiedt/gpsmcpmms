# Anleitung zu Übersetzungen

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
- Der Editor startet in der Sprache Ihres Browsers, sofern es dafür eine
  Übersetzung gibt, sonst auf Englisch. Über die Sprachauswahl (**Sprache**)
  in der obersten Zeile können Sie jederzeit wechseln.

---

## Schritt 1 — Administrator-Modus freischalten

1. Klicken Sie in der obersten Zeile auf **Geschützte Parameter anzeigen**.
2. Geben Sie das Administrator-Passwort ein.

Nun erscheinen zwei Schaltflächen: **Neue Übersetzung hinzufügen** und
**Vorhandene Übersetzung bearbeiten**.

---

## Schritt 2 — Vorlage (CSV) herunterladen

1. Klicken Sie auf **Neue Übersetzung hinzufügen** für eine Sprache, die das
   Gerät noch nicht hat, oder auf **Vorhandene Übersetzung bearbeiten**, um
   eine vorhandene zu verbessern. (Die zweite ist gesperrt, solange es nichts
   zu bearbeiten gibt, und sagt das auch: *Noch keine Übersetzung vorhanden*.)
2. Geben Sie für eine neue Sprache einen 2–3 Buchstaben langen **Sprachcode**
   ein, z. B. `fr`, `it` oder `es`, und als **Sprachname**, wie die Sprache sich
   selbst nennt — `Français`, nicht `Französisch`. Unter diesem Namen steht sie
   danach in jeder Sprachauswahl.

   Die beiden Felder sind allerdings nur dann beschreibbar, wenn das Gerät neue
   Sprachen frei zulässt. Bringt die Anwendung eine feste Liste erlaubter
   Sprachen mit, wählen Sie stattdessen im Auswahlfeld davor eine davon aus; die
   beiden Felder zeigen dann nur noch Code und Namen der gewählten Sprache an.
3. Setzen Sie in der Zeile darunter bis zu drei Häkchen bei bestehenden
   Sprachen: *Quellschlüssel übersetzen, mit bis zu 3 Sprachen als weiterem
   Kontext*. Sie geben einem menschlichen Übersetzer — oder einer KI — etwas zum
   Vergleichen.
4. Klicken Sie auf **CSV herunterladen**. Eine Datei namens `<code>.csv`
   (z. B. `fr.csv`) wird auf Ihrem Rechner gespeichert.

Die Datei ist eine UTF-8-Textdatei. Ihre Spalten sind:

| Spalte          | Bedeutung                                                              |
|-----------------|-----------------------------------------------------------------------|
| `en` (erste)    | Der zu übersetzende Text, so wie die Software ihn schreibt. **Nicht verändern.** |
| `kind`          | Was der Text ist und wo er erscheint (siehe unten). **Nicht verändern.** |
| Referenz(en)    | Bestehende Übersetzungen, nur zur Ansicht. **Nicht verändern.**        |
| `<code>` (letzte) | Die Zielsprache — **diese Spalte füllen Sie aus.**                  |

Die Spalte `kind` sagt Ihnen, worauf es bei dieser Zeile ankommt. Ein Text kann
mehreres zugleich sein; dann steht beides da, etwa `label, speech`.

| `kind`        | Was das für die Übersetzung heißt                                     |
|---------------|-----------------------------------------------------------------------|
| `label`       | Beschriftung neben einem Feld oder auf einer Schaltfläche — **kurz halten**, sonst bricht die Anzeige um. |
| `tooltip`     | Erklärender Text hinter dem Fragezeichen — hier ist Platz für einen ganzen Satz. |
| `placeholder` | Ein Formatbeispiel im Eingabefeld, etwa eine Rufnummer. Meist **unverändert übernehmen** (siehe unten). |
| `speech`      | Wird vom Gerät **vorgelesen**. Abkürzungen, Klammern und Sonderzeichen werden mitgesprochen; schreiben Sie es so, wie man es sagt. Ein Doppelpunkt erzeugt eine kurze, ein Zeilenumbruch eine ganze Sekunde Pause. |
| `ui`          | Bedienoberfläche des Editors selbst — Schaltflächen, Meldungen, Überschriften. |

Die Felder sind durch einen senkrechten Strich `|` getrennt, und jedes Feld ist
in doppelte Anführungszeichen eingeschlossen (damit Kommas und Semikolons
innerhalb eines Textes eine Zeile niemals zerreißen können).

---

## Schritt 3 — Übersetzungen eintragen

- Bearbeiten Sie **nur die letzte Spalte** (Ihre Zielsprache). Lassen Sie alle
  Spalten links davon unverändert — sie sind die Quelle und der Kontext.
- Ein **leeres** Feld bedeutet „noch nicht übersetzt“; dieser Eintrag erscheint
  dann im Wortlaut seines Schlüssels, und die Sprache gilt so lange als
  unvollständig. Sie dürfen einige Einträge jetzt und den Rest später übersetzen.
- Soll ein Eintrag **unverändert übernommen** werden, dann **wiederholen Sie den
  Text des Schlüssels** in Ihrer Spalte. Leer lassen genügt dafür nicht: leer heißt
  „fehlt noch“, wiederholt heißt „ich habe hingesehen, so bleibt es“. Das kommt
  öfter vor, als man denkt — bei einem Wort, das in Ihrer Sprache genauso lautet
  („OK“), und bei Feldern, hinter denen gar kein Satz steckt, etwa dem
  Formatbeispiel `004961501834300` für eine Rufnummer.
- Sie können von Hand übersetzen oder die gesamte Datei einem KI-Assistenten
  übergeben. Quelltext, `kind` und die Referenzspalten liefern alles Nötige.

### Die Datei einem KI-Assistenten übergeben

Hängen Sie die heruntergeladene `<code>.csv` an und geben Sie eine Anweisung wie
die folgende. Ersetzen Sie `<SPRACHE>` durch die gewünschte Sprache und
`<code>` durch den Spaltennamen, und lassen Sie die Regeln stehen — jede von
ihnen steht da, weil ihr Fehlen eine Datei erzeugt, die zwar richtig aussieht,
aber etwas kaputt macht.

> Du übersetzt die Bedienoberfläche eines Konfigurationseditors ins
> **\<SPRACHE\>**. Die angehängte `<code>.csv` ist eine UTF-8-Textdatei, eine
> Zeile je Zeichenkette, Felder durch `|` getrennt, jedes Feld in doppelten
> Anführungszeichen.
>
> Die erste Spalte ist der Quelltext, den du übersetzt. Dann `kind` (was der
> Text ist), möglicherweise weitere Referenzsprachen als Kontext, und zuletzt
> die Zielspalte `<code>` — die einzige Spalte, in die du schreiben darfst.
>
> 1. Gib die **vollständige** Datei zurück: jede Zeile, in derselben
>    Reihenfolge, im selben Format, nichts hinzugefügt, nichts weggelassen,
>    nichts zusammengefasst oder abgekürzt.
> 2. Fülle **nur die letzte Spalte**. Übernimm alle Spalten links davon
>    unverändert.
> 3. Alles in geschweiften Klammern — `{n}`, `{langs}`, `{max}`, `{service}`,
>    `{scope}` — ist ein Platzhalter, den die Software zur Laufzeit einsetzt.
>    Übernimm ihn genau so, samt Klammern und Schreibweise darin. Du darfst ihn
>    im Satz verschieben, wenn die Grammatik von \<SPRACHE\> es verlangt. Für
>    `{scope}` wird eine andere Zeile derselben Datei eingesetzt — lass die
>    runden Klammern darum stehen, wo der Quelltext sie hat, und schreibe die
>    Wörter nicht selbst hinein.
> 4. Beachte die Spalte `kind`:
>    - `label` — Beschriftung neben einem Feld oder auf einer Schaltfläche:
>      **kurz halten**.
>    - `tooltip` — erklärender Text: ein ganzer Satz ist in Ordnung.
>    - `placeholder` — ein Formatbeispiel, etwa eine Rufnummer: den Quelltext
>      unverändert wiederholen, es sei denn, das Format ist in \<SPRACHE\>
>      wirklich ein anderes.
>    - `speech` — wird von einem Gerät **vorgelesen**, einem älteren Menschen,
>      der vielleicht gerade um Hilfe bittet. Schreibe es so, wie man es sagt:
>      keine Abkürzungen, keine Klammern, keine Sonderzeichen. Behalte die
>      Satzzeichen, denn ein Doppelpunkt wird zu einer kurzen und ein
>      Zeilenumbruch zu einer einsekündigen Pause. Sprich die zuhörende Person
>      höflich an.
>    - `ui` — Schaltflächen und Meldungen des Editors selbst, gelesen von einer
>      administrierenden Person.
> 5. Ist ein Text in \<SPRACHE\> schon richtig, wie er dasteht — etwa ein Wort,
>    das genauso lautet —, dann **wiederhole ihn** statt die Zelle leer zu
>    lassen. Eine leere Zelle heißt „noch nicht übersetzt“.
> 6. Nutze die anderen Spalten als Kontext, wenn ein Text kurz oder mehrdeutig
>    ist.
> 7. Verwende die Anführungszeichen und Satzzeichen, wie sie in \<SPRACHE\>
>    üblich sind.
>
> Gib zuerst die Datei zurück. Falls du irgendwo raten musstest, nenne diese
> Zeilen danach kurz.

Zwei Dinge lohnt es, an der Antwort zu prüfen, bevor Sie sie hochladen: dass sie
**so viele Zeilen hat wie die Datei, die Sie gesendet haben**, und dass kein
`{…}`-Platzhalter übersetzt oder verloren gegangen ist. Um das Übrige kümmert
sich das Hochladen — eine Zeile, mit der es nichts anfangen kann, steht im
Bericht und verschwindet nicht stillschweigend.

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

1. Die dritte Zeile des Bereichs nennt die Reihenfolge:
   *Übersetzungsdatei: zuerst* … *dann* … *zuletzt*. Klicken Sie auf
   **Fertige CSV auswählen** und wählen Sie Ihre ausgefüllte `<code>.csv`.
2. Klicken Sie auf **Ausgewählte CSV hochladen**.
3. Ein Bericht namens `<code>.report.csv` wird automatisch heruntergeladen, und
   eine kurze Meldung zeigt, wie viele Einträge übersetzt wurden
   (z. B. *„37 / 152 übersetzt“*).

Behalten Sie den Dateinamen `<code>.csv` bei, damit der Editor die Zielsprache
erkennt; andernfalls werden Sie nach dem Code gefragt. Die Datei muss eine
**echte CSV-Datei (Text)** sein — eine Excel-Arbeitsmappe **`.xlsx`** wird mit
einer klaren Meldung abgelehnt. Laden Sie also stets die `.csv` hoch.

---

## Schritt 5 — Bericht lesen

Die **Status**-Spalte des Berichts ist englisch und bedeutet:

| Status                 | Bedeutung                                                     |
|------------------------|---------------------------------------------------------------|
| `applied`              | Ihre Übersetzung wurde übernommen                              |
| `no translation`       | das Feld wurde leer gelassen                                  |
| `unchanged`            | die Zeile war nicht in Ihrer Datei; der bisherige Wert bleibt  |
| `not in file`          | die Zeile war nicht in Ihrer Datei und hatte auch bisher keine Übersetzung |
| `skipped: unknown key` | dieser Schlüssel wird nicht mehr verwendet und wurde übergangen |

Wechseln Sie die Sprachauswahl auf Ihren Zielcode, um das Ergebnis direkt im
Editor zu sehen.

---

## Gut zu wissen

- Es können **bis zu sieben Sprachen** gleichzeitig bestehen. Fügen Sie eine
  achte hinzu, fragt der Editor, welche bestehende entfallen soll. **Englisch**
  und **Deutsch** lassen sich nicht entfernen: in Englisch sind die Schlüssel
  geschrieben, und Deutsch ist die Sprache, für die dieses Projekt gebaut ist.
- Eine Sprache braucht keine Übersetzung der Schlüssel, die schon in ihr
  geschrieben sind — die zählen als erledigt. Deshalb meldet ein Gerät, dessen
  Anwendung deutsch geschrieben ist, Deutsch als vollständig, ohne dass jemand
  seine Beschriftungen ins Deutsche übersetzt hätte.
- Übersetzungen dürfen **unvollständig** bleiben: alles Nichtübersetzte wird im
  Wortlaut seines Schlüssels angezeigt, und ein erneutes Herunterladen der
  Vorlage zeigt Ihren gespeicherten Fortschritt, sodass Sie jederzeit
  weitermachen können.
- Manchmal finden Sie **eine Zeile, wo Sie zwei erwarten würden**. Schreibt die
  Anwendung eine Beschriftung, die Wort für Wort dem entspricht, was der Editor
  in dieser Sprache ohnehin sagt, sind beide ein Eintrag: Sie übersetzen ihn
  einmal, und beide verwenden Ihre Fassung. Die Spalte `kind` nennt dann beide
  Verwendungen.
- Klicken Sie am Ende auf **Sitzung beenden**, damit ein anderer Administrator
  bearbeiten kann.
