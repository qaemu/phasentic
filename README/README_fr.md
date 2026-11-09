<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="../assets/wordmark-dark.svg">
    <img src="../assets/wordmark-light.svg" alt="phasentic" width="360">
  </picture>
</p>

<p align="center">
  Identification de phases par diffraction des rayons X sur poudre, avec une méthode validée et reproductible.
</p>

<p align="center">
  <a href="../README.md">English</a> | <a href="README_es.md">Español</a> | <b>Français</b> | <a href="README_cn.md">简体中文</a> | <a href="README_ar.md">العربية</a> | <a href="README_de.md">Deutsch</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10%E2%80%933.13-3776ab" alt="Python 3.10–3.13">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="Licence MIT"></a>
</p>

<p align="center">
  <a href="#install">Installation</a> ·
  <a href="#quick-start">Démarrage rapide</a> ·
  <a href="#how-accurate-is-it">Validation</a> ·
  <a href="../docs/">Documentation</a>
</p>

Phasentic lit un diffractogramme de poudre (`.xy`, `.xrdml` ou `.raw` ASCII),
détecte les pics, interroge une base de données de référence construite à partir de la
[Crystallography Open Database](https://www.crystallography.net/cod/) (ou de [POW_COD](https://www.ba.ic.cnr.it/softwareic/qualx/) du CNR)
et ajuste des mélanges de cinq phases au plus. Il renvoie des hypothèses de
phases classées et consigne tous les paramètres, empreintes et avertissements
dans un rapport JSON. Il fonctionne en local, dans le navigateur ou en ligne de
commande.

<p align="center">
  <img src="../docs/images/interface.png" alt="Interface de Phasentic : un résultat provisoire avec ZrO2, le graphique d’ajustement, les hypothèses concurrentes et les alternatives par phase" width="900">
  <br>
  <sub>Un diffractogramme de développement du jeu de données Precursor Genome (PG_2452, Cu Kα), tiré au hasard. Phasentic retient ZrO₂. L’étiquette affinée par un expert contient aussi deux phases minoritaires : LiOH·H₂O, qui n’apparaît que dans les hypothèses concurrentes (ZrO₂ + LiH₃O₂), et Li₂CO₃, que cette analyse ne détecte pas.</sub>
</p>

<a name="how-accurate-is-it"></a>
## Quelle est sa précision

Les paramètres ont été ajustés sur 485 diffractogrammes de Precursor Genome
(étiquettes affinées par des experts), puis appliqués à 200 diffractogrammes
verrouillés que l’ajustement n’a jamais vus, avec la base de données
PXRD_COD 2026.11 (issue de COD, complétée par Materials Project). Les
abstentions comptent comme des échecs.

| Niveau | Corrects | Taux |
|---|---|---|
| Bons composés et bonnes structures cristallines (strict) | 85 / 200 | 42,5 % |
| Bons composés, polymorphe quelconque (famille) | 104 / 200 | 52,0 % |

C’est la deuxième exécution sur ces 200 diffractogrammes. La première (72 et 99)
utilisait la base COD seule ; le complément de la base, les formules dont
l’hydrogène a été restauré et la préférence pour la description de plus haute
symétrie d’un matériau ont été mis au point uniquement sur les 485
diffractogrammes d’ajustement. La méthode non ajustée obtenait 71 et 96. Ces
chiffres valent pour le préréglage validé avec PXRD_COD 2026.11, le Cu Kα et la
chimie des précurseurs de l’échantillon ; les autres réglages ne sont pas
testés.

<a name="install"></a>
## Installation

L’installation comprend Python 3.12, Phasentic et sa base de données de
référence (un téléchargement de 8,6 Go depuis Zenodo ; prévoir environ 10 Go
libres). Aucun droit d’administrateur n’est nécessaire.

Windows : collez ces quatre lignes dans PowerShell (la première est
l’installateur officiel de [uv](https://docs.astral.sh/uv/), qui installe
Python) :

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/tags/v1.0.0.zip
phasentic setup
```

macOS et Linux :

```bash
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/v1.0.0/install.sh | sh
```

Sous Windows, `phasentic setup` télécharge la base de données, ajoute un
raccourci **Phasentic** sur le Bureau et dans le menu Démarrer et ouvre
Phasentic dans sa propre fenêtre ; fermez Phasentic avant de réinstaller. Sous
macOS, l’installateur ajoute Phasentic aux Applications, sous Linux au menu des
applications. Si le téléchargement est interrompu, relancez les mêmes
commandes ; il reprend là où il s’était arrêté.

### Utiliser POW_COD à la place

Si vous disposez de **POW_COD 2205 (FULL)** depuis la
[page de téléchargement du CNR](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/),
installez-le avec la commande ci-dessous ; Phasentic l’utilise alors à la place
de la base COD. Les chiffres de précision publiés ont été mesurés avec la base
COD, pas avec POW_COD.

```bash
phasentic setup-powcod ~/Downloads/powcod-2205.zip
```

<a name="quick-start"></a>
## Démarrage rapide

Ouvrez Phasentic depuis son raccourci ou lancez `phasentic-app`. Pour
l’utiliser dans un navigateur, lancez la commande ci-dessous et ouvrez
<http://127.0.0.1:8000> :

```bash
phasentic serve
```

Déposez un diffractogramme sur la fenêtre (ou choisissez-le), saisissez les
formules des précurseurs et des cibles et cliquez sur *Analyze*. Avec des
formules et le Cu Kα, la méthode validée est utilisée ; la tolérance de pics et
le nombre maximal de phases se modifient dans *Search settings*, et les autres
valeurs ne sont pas validées. *PDF* enregistre un rapport simple des valeurs
mesurées et calculées ; *Formal report* ouvre un rapport imprimable (graphique
d’ajustement, éléments probants par phase, hypothèses concurrentes, méthode et
traçabilité) ; *CIF* et *JSON* fournissent les données. L’interface est en
anglais et en espagnol.

En ligne de commande, la même méthode validée :

```bash
phasentic analyze scan.xrdml --preset validated --chemistry "Ag2O BaCO3 Ba2Ag2C2O7" --output report.json
```

`--chemistry` limite les candidats aux éléments de ces formules, plus H, C et O
(carbonates, hydroxydes, hydrates). Sans `--preset`, chaque paramètre de
l’analyse peut être réglé par des options (`phasentic analyze --help`) ; ces
combinaisons ne sont pas validées.

Les résultats sont au mieux `tentative` (ou `ambiguous` / `unresolved`) : une
décision `supported` nécessiterait un étalonnage des positions de raies joint
au résultat, que cette version ne propose pas. `phasentic calibrate standard.xy`
vérifie toujours les positions de raies d’un instrument à l’aide d’un
diffractogramme étalon (silicium NIST SRM 640g par défaut).

## Quand ne pas l’utiliser

- **Pour des fractions de phases.** Les échelles d’ajustement sont des
  amplitudes de criblage, pas des pourcentages massiques.
- **Pour des échantillons à trois phases ou plus**, pour lesquels il n’a
  identifié tous les composés que dans 11 % des cas lors des tests.
- **Pour des phases minoritaires ou faiblement diffusantes** (par exemple des
  sels de Li, B ou K à côté de phases d’éléments lourds), qu’il manque souvent.

## Fonctionnement

1. Importe le diffractogramme, estime le fond et détecte les pics (en tenant compte du bruit).
2. Cherche des candidats dans la base de référence, limités aux éléments de l’échantillon.
3. Ajuste des mélanges non négatifs de profils de référence par une recherche
   en faisceau bornée, avec de nouvelles requêtes sur le résidu et des échanges
   de phases ; rejette les phases dont les raies fortes manquent dans le
   diffractogramme.
4. Classe les hypothèses, signale l’ambiguïté et consigne la provenance
   (empreinte de l’entrée, paramètres, identité de la base, versions des
   algorithmes).

Détails : [docs/scientific-method.md](../docs/scientific-method.md) et
[PARAMETERS.md](../PARAMETERS.md).

## Citer

Si Phasentic contribue à vos travaux, citez la version utilisée. Le bouton
*Cite this repository* de GitHub (à partir de [CITATION.cff](../CITATION.cff))
fournit les formats APA et BibTeX. Citez aussi la base de référence,
[PXRD_COD 2026.11](https://doi.org/10.5281/zenodo.24059658), et ses sources :
la Crystallography Open Database et le Materials Project (et POW_COD si vous
l’utilisez à la place).

## Licence

MIT pour le code. La base de référence est sous CC BY 4.0 (données COD CC0,
données Materials Project CC BY 4.0). Les données de POW_COD et de Precursor
Genome sont distribuées selon leurs propres conditions et ne sont pas incluses
dans ce dépôt.
