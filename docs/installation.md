# Installation

Phasentic needs Python 3.10–3.13 on Linux, macOS or Windows.

## The `phasentic` command

```bash
pipx install git+https://github.com/qaemu/phasentic
# or: uv tool install git+https://github.com/qaemu/phasentic
# or: pip install git+https://github.com/qaemu/phasentic
phasentic --version
```

If you don't have `pipx`: `python -m pip install --user pipx && python -m pipx ensurepath`,
then open a new terminal.

## POW_COD (once)

Download **POW_COD 2205 (FULL)** from the
[CNR page](https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/), then:

```bash
phasentic setup-powcod path/to/powcod-2205.zip
```

It verifies the archive's SHA-256, extracts it to `~/.phasentic/powcod`
(set `PHASENTIC_HOME` to use another folder; you need about 9 GB free) and
builds the query cache. From then on POW_COD is the default reference.
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
