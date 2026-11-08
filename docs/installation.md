# Installation

Phasentic runs on Linux, macOS and Windows.

## Install

Installs uv, Python 3.12, Phasentic and the COD reference database (8.6 GB
from Zenodo; about 10 GB free disk needed). No admin rights needed.

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
uv tool install --force --python 3.12 https://github.com/qaemu/phasentic/archive/refs/heads/main.zip
phasentic setup
```

```bash
# macOS and Linux
curl -LsSf https://raw.githubusercontent.com/qaemu/phasentic/main/install.sh | sh
```

Running it again resumes an interrupted download and leaves a correct
installation alone. The database goes to `~/.phasentic/cod` (set
`PHASENTIC_HOME` to use another folder).

## POW_COD instead of COD (optional)

Download **POW_COD 2205 (FULL)** from the
[CNR page](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/), then:

```bash
phasentic setup-powcod path/to/powcod-2205.zip
```

It verifies the archive's SHA-256, extracts it to `~/.phasentic/powcod`
(about 9 GB free needed) and builds the query cache. When POW_COD is
installed, Phasentic uses it instead of the COD database.
Manual alternatives are in [cod-database.md](cod-database.md).

## From a clone (development)

```bash
git clone https://github.com/qaemu/phasentic && cd phasentic
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
```

## Optional: binary vendor `.raw` files

Binary Bruker/Rigaku `.raw` files are read through a local GSAS-II
installation, used for import only. Point `GSASII_PATH` at it; supported
formats are listed in `src/phasentic/resources/gsas2-vendor-mappings.json`.
Without it, export the scan as `.xy` or `.xrdml`.
