# Reference databases

Phasentic uses the CNR POW_COD 2205 SQLite release as its production
screening reference. POW_COD is a derived database generated from COD structure
information and contains precomputed d-spacings, hkl values, multiplicities
where supplied, and relative intensities. It is much smaller and faster to use
than recalculating every COD CIF at application start.

The download is an external operator-owned asset. CNR describes academic and
non-profit access as free, but the download portal may require registration and
acceptance of its terms. Preserve the downloaded archive, its SHA-256, the
companion `.sq.info` file when supplied, and the generated manifest under an
ignored local directory such as `data/references/powcod/`. The binary is not
downloaded implicitly. A future GitHub release should include these
installation instructions and a checksum-bound asset or release link; it must
not place the large database in ordinary Git history without a confirmed
redistribution grant.

## Obtain the local testing asset

Use the official CNR page for **POW_COD 2205 (FULL)**:

<https://www.ba.ic.cnr.it/softwareic/qualx/download/powcod-2205/>

Download the ZIP manually, save it outside Git, and record its hash before
extracting it:

```bash
mkdir -p data/references/powcod/raw
shasum -a 256 ~/Downloads/POW_COD-2205.zip \
  | tee data/references/powcod/raw/POW_COD-2205.zip.sha256
unzip ~/Downloads/POW_COD-2205.zip -d data/references/powcod/raw
find data/references/powcod/raw -type f \( -name '*.sq' -o -name '*.info' \) -print
```

The CNR 2205 archive used for the current local test was 1,923,506,012 bytes
with SHA-256
`75b74f9544e8677edb2c6dc46196ee4331e27f21d943a70b08c68f18c010f9df`. Treat
that value as an asset identity for reproducibility; verify the checksum again
when obtaining the file from a future release mirror.

The archive name and extracted database name can vary. Use the extracted
`.sq` path in the preparation command below, and pass the matching `.sq.info`
when CNR supplies one. Do not commit the ZIP, SQLite database, cache, or
manifest; `.gitignore` reserves `data/references/powcod/` for this purpose.

## Install and prepare

The quickest path is one command, which does everything below for the default
location `~/.phasentic/powcod`:

```bash
phasentic setup-powcod path/to/powcod-2205.zip
```

The manual steps, if you keep POW_COD elsewhere:

After obtaining the CNR archive and extracting `powcod.sq` (and, for the full
release, `powcod.sq.info`), create the normalized query cache:

```bash
phasentic powcod prepare \
  data/references/powcod/powcod.sq \
  --info data/references/powcod/powcod.sq.info \
  --cache data/references/powcod/powcod-2205.xrd.sqlite \
  --manifest data/references/powcod/powcod-2205.manifest.json
```

The command reads the source databases only, writes an atomic sidecar cache,
and records the source and cache hashes, release, schema, row counts,
attribution, and license note. It rejects an unknown POW_COD schema. To avoid
scanning several gigabytes twice, preparation performs read-only schema and
row validation; the exhaustive SQLite integrity scan belongs to the explicit
`powcod verify` command below. The cache
stores one compressed reflection blob per phase plus a compact d-spacing
bitset index; it does not expand the release into hundreds of millions of
SQLite rows. A measurement uses the bitset index first and decodes only
candidate phases with reflections near the observed peaks. D spacings above
the indexed 100 Å range use a documented overflow bucket and are still kept in
the per-phase blobs.

The full release can return a very large candidate set for common d-spacing
windows (a silicon-like scan produced roughly 400,000 indexed candidates for
one peak at the default tolerance). The cache and retrieval path are therefore
validated, but broad full-database analysis still needs a bounded second-stage
ranking or candidate cap before it is suitable as an interactive workflow. Do
not interpret a successful cache build as a claim that a full-COD query is fast
or that its hypotheses are laboratory-grade.

Verify the installation:

```bash
phasentic powcod verify \
  data/references/powcod/powcod.sq \
  --cache data/references/powcod/powcod-2205.xrd.sqlite \
  --info data/references/powcod/powcod.sq.info
```

The source databases are opened read-only and fully integrity-checked by this
command. If their size or modification identity changes after cache creation,
verification fails with `POWCOD_SOURCE_CHANGED` and the cache must be rebuilt.
A missing cache fails with
`POWCOD_CACHE_NOT_FOUND`; the application never falls back to the demo source
after a POW_COD request.

## Runtime selection

Configure the localhost service with trusted local paths:

```bash
export PHASENTIC_REFERENCE_SOURCE=pow_cod
export PHASENTIC_POWCOD_PATH="$PWD/data/references/powcod/powcod.sq"
export PHASENTIC_POWCOD_CACHE_PATH="$PWD/data/references/powcod/powcod-2205.xrd.sqlite"
export PHASENTIC_POWCOD_EQUIVALENCE_PATH="$PWD/data/references/powcod/powcod-2205.equivalence.sqlite"
phasentic serve
```

For a headless run, the path may be supplied by the trusted CLI operator:

```bash
phasentic analyze sample.xy \
  --reference-source pow_cod \
  --powcod-db data/references/powcod/powcod.sq \
  --powcod-cache data/references/powcod/powcod-2205.xrd.sqlite
```

## Curated equivalence sidecar

POW_COD can contain multiple entries for the same phase. The optional
equivalence sidecar collapses only manually reviewed exact groups while
retaining every original COD entry in report provenance. Formula-only or
family-level similarities are never merged automatically, and distinct
polytypes remain separate unless explicitly curated.

Build it from the versioned curation input after the source and cache have
been verified:

```bash
phasentic powcod equivalence-build \
  data/references/powcod/powcod.sq \
  --cache data/references/powcod/powcod-2205.xrd.sqlite \
  --input configs/powcod-equivalence-curated.json \
  --output data/references/powcod/powcod-2205.equivalence.sqlite
```

The sidecar is hash-bound to both POW_COD files and fails closed when either
asset changes. Its curated content hash and method version are included in
analysis provenance. Parent mineral-family matches are reported as separate
partial evidence and do not become exact phase identifications.

The HTTP API accepts only the source name. It never accepts an arbitrary client
filesystem path; the server uses `PHASENTIC_POWCOD_PATH` and
`PHASENTIC_POWCOD_CACHE_PATH`. The GUI enables POW_COD only when the configured
source and cache pass verification.

## Radiation and scientific boundary

POW_COD d-spacings are portable across the project’s Cu, Co, Cr, Mo, and Ag
presets through Bragg’s law. The first integration uses the native POW_COD
relative-intensity path for Cu Kα; the release calculation configuration must
still be verified against the acquired asset. Co, Cr, Mo, and Ag use a
permanent position/d-spacing-only policy: their stored relative intensities are
not scored and reports carry `POWCOD_INTENSITY_UNSUPPORTED`. They are never
silently treated as radiation-independent experimental truth.

Non-Cu intensity scoring is outside the current product contract and must not be
enabled by configuration or a benchmark.
POW_COD alone does not provide experimental broadening, preferred orientation,
background, calibration uncertainty, or solid-solution shifts. Results remain
screening hypotheses and do not establish quantitative phase fractions or
laboratory-grade certainty.
