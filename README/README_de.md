<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  Phasenidentifizierung aus Pulver-Röntgenbeugungsdaten mit einer validierten, reproduzierbaren Methode.
</p>

<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <a href="README_fr.md">Français</a> | <a href="README_cn.md">简体中文</a> | <a href="README_ar.md">العربية</a> | <b>Deutsch</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT-Lizenz"></a>
</p>

<p align="center">
  <a href="#install">Installation</a> ·
  <a href="#quick-start">Schnellstart</a> ·
  <a href="#how-accurate-is-it">Validierung</a> ·
  <a href="../docs/">Dokumentation</a> ·
  <a href="#how-this-was-built">Wie dieses Projekt entstand</a>
</p>

Phasentic liest einen Pulver-XRD-Scan (`.xy`, `.xrdml` oder ASCII-`.raw`) ein,
detektiert die Reflexe, durchsucht die Referenzdatenbank
[POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) des CNR und passt Gemische
aus bis zu fünf Phasen an. Als Ergebnis liefert es eine Rangliste von
Phasenhypothesen; jede Einstellung, jeder Hash und jede Warnung wird in einem
JSON-Bericht festgehalten. Phasentic läuft lokal, im Browser oder auf der
Kommandozeile.

<p align="center">
  <img src="../docs/images/interface.png" alt="Phasentic-Oberfläche: ein vorläufiges Ergebnis aus ZrO2 und LiOH·H2O mit dem Anpassungsplot und den konkurrierenden Hypothesen" width="900">
  <br>
  <sub>Ein zufällig ausgewählter Entwicklungsscan aus dem Datensatz Precursor Genome (PG_2452, Cu Kα). Phasentic findet ZrO₂ und LiOH·H₂O; die manuell verfeinerte Referenzzuordnung enthält zusätzlich Li₂CO₃, das in diesem Lauf übersehen wird. Das verbleibende Signal ist unter <i>Evidence per phase</i> (Belege je Phase) sichtbar.</sub>
</p>

<a name="how-accurate-is-it"></a>

## Wie genau ist die Methode?

Die Methode wurde vor dem Test zusammen mit einem vorab festgelegten Zielwert
eingefroren und einmalig auf 200 Scans angewendet, die sie nie zuvor gesehen
hatte (Precursor Genome, manuell verfeinerte Referenzzuordnungen). Fälle ohne
Ergebnis (Enthaltungen) zählen als Fehlschläge.

| Ebene | Korrekt | Trefferquote | 95%-Intervall (Wilson) | Festgelegter Zielwert |
|---|---|---|---|---|
| Richtige Verbindungen und Kristallstrukturen (strict) | 74 / 200 | 37.0% | 30.6–43.9% | ≥ 35% |
| Richtige Verbindungen, beliebiges Polymorph (family) | 99 / 200 | 49.5% | 42.6–56.4% | ≥ 45% |

Beide Punktschätzungen erreichen ihren Zielwert; beide Untergrenzen liegen darunter.
Die Genauigkeit hängt stark von der Anzahl der Phasen ab:

| Phasen in der Probe | Scans | Korrekt auf Familienebene (family) |
|---|---|---|
| 1 | 8 | 3 |
| 2 | 125 | 87 (70%) |
| 3 oder mehr | 67 | 9 (13%) |

Das Protokoll, der frühere Lauf auf einem zurückgehaltenen Testdatensatz
(32% / 42% für die Vorgängerversion), die Fehleranalyse und die Nachweise
stehen in [docs/validation.md](../docs/validation.md). Diese Zahlen gelten für
die validierte Konfiguration (Preset) mit POW_COD, Cu Kα und der
Präkursorchemie der Probe; andere Einstellungen wurden nicht getestet.

<a name="install"></a>

## Installation

Benötigt wird Python 3.10–3.13. Am einfachsten wird der Befehl `phasentic` in
einer eigenen Umgebung installiert:

```bash
pipx install git+https://github.com/qaemu/phasentic
```

oder mit [uv](https://docs.astral.sh/uv/): `uv tool install git+https://github.com/qaemu/phasentic`,
oder mit einfachem pip: `pip install git+https://github.com/qaemu/phasentic`.

Installation prüfen:

```bash
phasentic --version
```

### Referenzdatenbank POW_COD hinzufügen (einmalig)

Ohne POW_COD arbeitet Phasentic mit einer Demo-Teilmenge aus drei Phasen, die sich
nur zum Ausprobieren der Oberfläche eignet. Für die eigentliche Arbeit:

1. **POW_COD 2205 (FULL)** (etwa 1.9 GB) von der
   [Download-Seite des CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/) herunterladen.
2. Ausführen:

   ```bash
   phasentic setup-powcod ~/Downloads/powcod-2205.zip
   ```

Dabei wird das Archiv geprüft, nach `~/.phasentic/powcod` entpackt (etwa 6 GB)
und einmalig ein Abfrage-Cache erstellt (20–60 Minuten). Danach verwendet
Phasentic standardmäßig POW_COD.

<a name="quick-start"></a>

## Schnellstart

Die lokale Oberfläche starten und <http://127.0.0.1:8000> öffnen:

```bash
phasentic serve
```

Einen Scan auswählen, die Formeln der Präkursoren und des Zielprodukts
eingeben, *Validated method* (validierte Methode) ausgewählt lassen (Standard)
und auf *Analyze* (Analysieren) klicken. *Download report* (Bericht
herunterladen) erzeugt einen druckbaren zweiseitigen Bericht (Anpassungsplot,
Belege je Phase, konkurrierende Hypothesen, Methode und Rückverfolgbarkeit),
der sich als PDF speichern lässt; *JSON* liefert den vollständigen
maschinenlesbaren Gesamtdatensatz.

Auf der Kommandozeile dieselbe validierte Methode:

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` beschränkt die Kandidaten auf die Elemente dieser Formeln sowie
H, C und O (Carbonate, Hydroxide, Hydrate). Ohne `--preset` lässt sich jede
Analyseeinstellung über Flags anpassen (`phasentic analyze --help`); diese
Kombinationen sind nicht validiert.

Eine Entscheidung `supported` erfordert zusätzlich eine Kalibrierung der
Reflexlagen mit dem Scan einer Referenzprobe (standardmäßig Silicium
NIST SRM 640g): `phasentic calibrate standard.xy`.

## Wann Phasentic nicht geeignet ist

- **Als Nachweis, dass eine Phase vorliegt.** Die Ergebnisse sind Hypothesen in
  Rangfolge, die von Fachleuten zu bestätigen sind, idealerweise durch
  Rietveld-Verfeinerung.
- **Für Phasenanteile.** Die Skalierungsfaktoren der Anpassung sind
  Screening-Amplituden, keine Gewichtsprozente.
- **Für Proben mit drei oder mehr Phasen**, bei denen im Test nur in 13% der
  Fälle alle Verbindungen identifiziert wurden.
- **Für Neben- oder schwach streuende Phasen** (zum Beispiel Li-, B- oder
  K-Salze neben Phasen schwerer Elemente), die häufig übersehen werden.
- **Ohne Angabe der Probenchemie oder mit anderen Anoden als Cu**, da diese
  nicht Teil der Validierung waren.

## Funktionsweise

1. Scan importieren, Untergrund schätzen, Reflexe detektieren (unter
   Berücksichtigung des Rauschens).
2. Kandidaten aus POW_COD abrufen, beschränkt auf die Elemente der Probe.
3. Nichtnegative Gemische von Referenzprofilen anpassen, mit einer begrenzten
   Strahlsuche (beam search), erneuten Abfragen anhand des Residuums und
   Phasentausch; Phasen verwerfen, deren starke Reflexe im Scan fehlen.
4. Hypothesen in eine Rangfolge bringen, Mehrdeutigkeiten ausweisen und die
   Herkunft protokollieren (Eingabe-Hash, Einstellungen, Datenbankidentität,
   Algorithmusversionen).

Details: [docs/scientific-method.md](../docs/scientific-method.md) und
[PARAMETERS.md](../PARAMETERS.md).

## Reproduktion der Validierung

Repository klonen und installieren:

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
pip install -e .
```

Die validierten Läufe verwenden `scripts/run_wp5_parallel.py`; das Skript
verweigert die Ausführung, wenn der Analysecode vom Hash in der eingefrorenen
Konfiguration (`validation/wp5-precursor-frozen-v5.json`) abweicht. Die
Falllisten der Kohorten und die Ergebnisnachweise liegen in
[`validation/`](../validation/); die Scans selbst stammen aus dem Datensatz
[Precursor Genome](https://github.com/lauren-walters/precursor-genome)
(CC BY 4.0). Eine Schritt-für-Schritt-Anleitung steht in
[docs/validation.md](../docs/validation.md).

<a name="how-this-was-built"></a>

## Wie dieses Projekt entstand

Phasentic wurde fast vollständig von **Claude Code**, dem Coding-Agenten von
Anthropic, unter meiner Leitung geschrieben. Ich entwickle das Projekt allein.
Ich habe das Problem, die Methoden und das Validierungsprotokoll gewählt, die
Ergebnisse geprüft und bin für jede Aussage in diesem Repository verantwortlich.

Alles, was die Aussagen überprüfbar macht, stand fest, bevor Ergebnisse
vorlagen: Der Genauigkeitszielwert wurde vor dem Tuning festgelegt,
für das Tuning wurden nur 100 Entwicklungsscans verwendet, der zurückgehaltene
Testdatensatz war versiegelt und wurde einmal ausgewertet, Einstellungen und
Code wurden per Hash eingefroren, und spätere Refactorings mussten alle 300
Ergebnisse exakt reproduzieren ([docs/validation.md](../docs/validation.md)).
Mit KI-Unterstützung erstellte Commits tragen den Trailer
`Assisted-by: Claude Code`. Siehe [AI_USE.md](../AI_USE.md).

## Zitieren

Wenn Phasentic zu Ihrer Arbeit beiträgt, bitte die verwendete Release-Version
zitieren. Die GitHub-Schaltfläche *Cite this repository* (auf Basis von
[CITATION.cff](../CITATION.cff)) liefert APA und BibTeX. Bitte zusätzlich POW_COD
und die Crystallography Open Database zitieren.

## Lizenz

MIT für den Code. Die Daten von POW_COD, COD und Precursor Genome werden unter
ihren eigenen Bedingungen verbreitet und sind nicht in diesem Repository
enthalten.
