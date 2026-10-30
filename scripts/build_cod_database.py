"""Build Phasentic's reference database from the Crystallography Open Database (COD).

One-time job, resumable at every stage (just run it again after a stop):

1. download the COD bulk archive (cod-cifs-mysql.tgz, ~27 GB);
2. stream every CIF out of it (nothing is unpacked to disk) and calculate its
   powder pattern with pymatgen: Cu Ka1, 2θ up to REFERENCE_TWO_THETA_MAX_DEG;
3. top up with entries added to COD after the archive date, fetched one by one;
4. build the query cache Phasentic reads (same format as the POW_COD cache).

Usage:
    python scripts/build_cod_database.py                # everything
    python scripts/build_cod_database.py --workers 6    # leave cores free

Then point Phasentic at it:
    PHASENTIC_REFERENCE_SOURCE=pow_cod
    PHASENTIC_POWCOD_PATH=<workdir>/cod-source.sq
    PHASENTIC_POWCOD_CACHE_PATH=<workdir>/cod.xrd.sqlite

COD data are CC0; credit the original authors of each structure.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import tarfile
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from multiprocessing import Pool
from pathlib import Path

from phasentic.domain.radiation import REFERENCE_TWO_THETA_MAX_DEG
from phasentic.references.factory import phasentic_home
from phasentic.references.powcod import build_powcod_cache

ARCHIVE_URL = "https://www.crystallography.net/archives/cod-cifs-mysql.tgz"
CIF_URL = "https://www.crystallography.net/cod/{}.cif"
OPTIMADE_URL = "https://www.crystallography.net/cod/optimade/v1/structures"
COD_TOTAL_HINT = 535_000  # for the ETA only
USER_AGENT = "phasentic-build-cod-database (https://github.com/qaemu/phasentic)"
TWO_THETA_MIN_DEG = 5.0


def http(url: str, *, headers: dict[str, str] | None = None, attempts: int = 5, timeout: int = 120):
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410, 416) or attempt == attempts - 1:
                raise
        except OSError:
            if attempt == attempts - 1:
                raise
        time.sleep(2 ** attempt)


def keep_awake() -> None:
    """Stop Windows from sleeping while this process runs (no-op elsewhere)."""

    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)  # CONTINUOUS | SYSTEM_REQUIRED


# ---------------------------------------------------------------- stage 1


def archive_info() -> tuple[int, datetime]:
    """Size and Last-Modified date of the COD bulk archive."""

    with http(ARCHIVE_URL, headers={"Range": "bytes=0-0"}) as head:
        return int(head.headers["Content-Range"].split("/")[-1]), parsedate_to_datetime(head.headers["Last-Modified"])


def download_archive(target: Path, total: int) -> None:
    """Download the bulk archive, resuming a partial file."""

    done = target.stat().st_size if target.exists() else 0
    if done == total:
        print(f"Archive already downloaded ({total / 1e9:.1f} GB).", flush=True)
        return
    print(f"Downloading COD archive {total / 1e9:.1f} GB (resuming at {done / 1e9:.1f} GB)...", flush=True)
    while done < total:
        try:
            with http(ARCHIVE_URL, headers={"Range": f"bytes={done}-"}, timeout=300) as response, target.open("ab") as out:
                started, start_bytes = time.monotonic(), done
                while chunk := response.read(4 * 1024 * 1024):
                    out.write(chunk)
                    done += len(chunk)
                    if done // (500 * 1024 * 1024) != (done - len(chunk)) // (500 * 1024 * 1024):
                        rate = (done - start_bytes) / max(time.monotonic() - started, 1e-9)
                        eta = (total - done) / max(rate, 1)
                        print(f"  {done / 1e9:.1f}/{total / 1e9:.1f} GB  {rate / 1e6:.1f} MB/s  ~{eta / 3600:.1f} h left", flush=True)
        except OSError as exc:  # dropped connection: resume from the current size
            print(f"  connection lost ({exc}); resuming in 10 s", flush=True)
            time.sleep(10)
    if target.stat().st_size != total:
        raise SystemExit(f"Archive size {target.stat().st_size} does not match {total}; delete it and rerun.")


# ---------------------------------------------------------------- stage 2/3: patterns


_TAG = {
    name: re.compile(rf"^{re.escape(tag)}[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    for name, tag in (
        ("mineral", "_chemical_name_mineral"),
        ("common", "_chemical_name_common"),
        ("systematic", "_chemical_name_systematic"),
        ("sg_alt", "_space_group_name_H-M_alt"),
        ("sg_old", "_symmetry_space_group_name_H-M"),
    )
}


def _tag(text: str, *names: str) -> str | None:
    for name in names:
        match = _TAG[name].search(text)
        if match:
            value = match.group(1).strip().strip("'\"").strip()
            if value and value not in {"?", "."}:
                return value
    return None


def pattern_row(item: tuple[str, str, int]) -> tuple:
    """Worker: (cod_id, cif_text, max_sites) -> ('ok', row) or ('skip'|'fail', cod_id, reason)."""

    cod_id, text, max_sites = item
    try:
        import warnings

        warnings.filterwarnings("ignore")
        from pymatgen.analysis.diffraction.xrd import XRDCalculator
        from pymatgen.io.cif import CifParser

        structure = CifParser.from_str(text).parse_structures(primitive=False)[0]
        if len(structure) > max_sites:
            return ("skip", cod_id, f"{len(structure)} sites > {max_sites}")
        pattern = XRDCalculator(wavelength="CuKa1").get_pattern(
            structure, two_theta_range=(TWO_THETA_MIN_DEG, REFERENCE_TWO_THETA_MAX_DEG)
        )
        if len(pattern.x) == 0:
            return ("skip", cod_id, "no reflections in range")
        hkls = [group[0]["hkl"] for group in pattern.hkls]
        lattice = structure.lattice
        return (
            "ok",
            (
                cod_id,
                ",".join(f"{d:.6f}" for d in pattern.d_hkls),
                ",".join(f"{y:.3f}" for y in pattern.y),
                ",".join(str(h[0]) for h in hkls),
                ",".join(str(h[1]) for h in hkls),
                ",".join(str(h[-1]) for h in hkls),  # hexagonal (h k i l) -> l
                structure.composition.reduced_formula,
                _tag(text, "mineral", "common", "systematic") or f"COD {cod_id}",
                _tag(text, "sg_alt", "sg_old") or "Unknown",
                lattice.a, lattice.b, lattice.c, lattice.alpha, lattice.beta, lattice.gamma,
            ),
        )
    except Exception as exc:  # one bad CIF must never stop a 2-day run
        return ("fail", cod_id, f"{type(exc).__name__}: {str(exc)[:200]}")


SCHEMA = """
CREATE TABLE IF NOT EXISTS id (
    id TEXT PRIMARY KEY, dvalue TEXT, intensita TEXT, h TEXT, k TEXT, l TEXT,
    formula TEXT, name TEXT, spacegroup TEXT, a REAL, b REAL, c REAL, alpha REAL, beta REAL, gamma REAL
);
CREATE TABLE IF NOT EXISTS skipped (id TEXT PRIMARY KEY, status TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


class Processor:
    """Feeds CIFs to a process pool with a bounded number in flight and stores results."""

    def __init__(self, db: sqlite3.Connection, workers: int, max_sites: int, label: str) -> None:
        self.db, self.max_sites, self.label = db, max_sites, label
        self.pool = Pool(workers, maxtasksperchild=500)
        self.slots = threading.BoundedSemaphore(workers * 4)
        self.results: collections.deque = collections.deque()
        self.done = {row[0] for row in db.execute("SELECT id FROM id UNION SELECT id FROM skipped")}
        self.counts = collections.Counter()
        self.started = time.monotonic()

    def submit(self, cod_id: str, text: str) -> None:
        self.slots.acquire()
        self.pool.apply_async(
            pattern_row, ((cod_id, text, self.max_sites),),
            callback=self._collect, error_callback=lambda exc: self._collect(("fail", cod_id, repr(exc))),
        )
        if len(self.results) >= 500:
            self.flush()

    def _collect(self, result: tuple) -> None:
        self.results.append(result)
        self.slots.release()

    def flush(self) -> None:
        ok, other = [], []
        while self.results:
            result = self.results.popleft()
            (ok if result[0] == "ok" else other).append(result)
        self.db.executemany("INSERT OR REPLACE INTO id VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [r[1] for r in ok])
        self.db.executemany("INSERT OR REPLACE INTO skipped VALUES (?,?,?)", [(r[1], r[0], r[2]) for r in other])
        self.db.commit()
        for result in ok + other:
            self.done.add(result[1][0] if result[0] == "ok" else result[1])
            self.counts[result[0]] += 1
        processed = sum(self.counts.values())
        if processed and processed // 2000 != (processed - len(ok) - len(other)) // 2000:
            rate = processed / max(time.monotonic() - self.started, 1e-9)
            left = max(COD_TOTAL_HINT - len(self.done), 0) / max(rate, 1e-9)
            print(
                f"  [{self.label}] {len(self.done)} entries done ({self.counts['ok']} ok, "
                f"{self.counts['skip']} skipped, {self.counts['fail']} failed this run)  "
                f"{rate * 3600:.0f}/h  ~{left / 3600:.1f} h left",
                flush=True,
            )

    def close(self) -> None:
        self.pool.close()
        self.pool.join()
        self.flush()


def process_archive(archive: Path, processor: Processor, limit: int | None) -> None:
    print("Calculating patterns from the archive (already-processed entries are skipped)...", flush=True)
    submitted = 0
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".cif"):
                continue
            cod_id = Path(member.name).stem
            if cod_id in processor.done:
                continue
            text = tar.extractfile(member).read().decode("utf-8", errors="replace")
            processor.submit(cod_id, text)
            submitted += 1
            if limit is not None and submitted >= limit:
                break


def modified_since(since: datetime) -> list[str]:
    """IDs of COD entries modified after ``since`` (paged OPTIMADE query)."""

    url = OPTIMADE_URL + "?" + urllib.parse.urlencode(
        {
            "filter": f'last_modified>"{since.astimezone(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"',
            "page_limit": 100,
            "response_fields": "id",
        }
    )
    ids: list[str] = []
    while url:
        with http(url) as response:
            page = json.load(response)
        ids.extend(item["id"] for item in page["data"])
        next_link = page.get("links", {}).get("next")
        url = next_link["href"] if isinstance(next_link, dict) else next_link
        if len(ids) % 10_000 < 100:
            print(f"  listed {len(ids)} of {page['meta'].get('data_returned')} modified entries", flush=True)
    return ids


def process_top_up(processor: Processor, since: datetime, refresh_modified: bool, limit: int | None) -> None:
    print(f"Listing COD entries modified after {since:%Y-%m-%d}...", flush=True)
    ids = modified_since(since)
    wanted = ids if refresh_modified else [i for i in ids if i not in processor.done]
    if limit is not None:
        wanted = wanted[:limit]
    print(f"Fetching {len(wanted)} entries one by one ({len(ids)} modified in total).", flush=True)
    for cod_id in wanted:
        try:
            with http(CIF_URL.format(cod_id)) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            processor.results.append(("fail", cod_id, f"download HTTP {exc.code}"))
            continue
        processor.submit(cod_id, text)


# ---------------------------------------------------------------- stage 4


def build_cache(source: Path, cache: Path, release: str) -> None:
    print("Building the query cache (single-threaded; can take a few hours)...", flush=True)
    result = build_powcod_cache(source, cache, release=release)
    # The cache builder labels its metadata for POW_COD; record what this really is.
    # Metadata rows are not part of cache_sha256, so the cache stays valid.
    with sqlite3.connect(cache) as db:
        db.executemany(
            "UPDATE metadata SET value=? WHERE key=?",
            (
                ("https://www.crystallography.net/cod/", "source_url"),
                ("COD data: CC0 public domain dedication", "license"),
                ("Crystallography Open Database; patterns calculated by Phasentic with pymatgen", "attribution"),
                (
                    f"pymatgen XRDCalculator, Cu Ka1, 2theta {TWO_THETA_MIN_DEG:g}-{REFERENCE_TWO_THETA_MAX_DEG:g} deg, "
                    "relative intensities scaled to 100",
                    "intensity_model",
                ),
            ),
        )
    print(f"Done: {result.phase_count} phases, {result.line_count} reflections, {cache.stat().st_size / 1e9:.1f} GB.")


# ---------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--workdir", type=Path, default=phasentic_home() / "cod")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--max-sites", type=int, default=3000, help="skip larger cells (a few take minutes each)")
    parser.add_argument("--archive", type=Path, help="use an already-downloaded cod-cifs-mysql.tgz")
    parser.add_argument("--refresh-modified", action="store_true", help="also re-fetch archive entries changed since")
    parser.add_argument("--since", help="top up entries modified after this ISO date (default: archive date)")
    parser.add_argument("--keep-archive", action="store_true", help="keep the 27 GB archive after processing")
    parser.add_argument("--limit", type=int, help="process at most N new entries per stage (trial runs)")
    args = parser.parse_args(argv)

    keep_awake()
    workdir = args.workdir.expanduser()
    workdir.mkdir(parents=True, exist_ok=True)
    source, cache = workdir / "cod-source.sq", workdir / "cod.xrd.sqlite"
    db = sqlite3.connect(source)
    db.executescript(SCHEMA)
    state = dict(db.execute("SELECT key, value FROM state"))

    archive = args.archive or workdir / "cod-cifs-mysql.tgz"
    if state.get("archive_done") != "1":
        total, archive_date = archive_info()
        if args.archive is None:
            download_archive(archive, total)
        db.execute("INSERT OR REPLACE INTO state VALUES ('archive_date', ?)", (archive_date.isoformat(),))
        db.commit()
        processor = Processor(db, args.workers, args.max_sites, "archive")
        process_archive(archive, processor, args.limit)
        processor.close()
        if args.limit is None:
            db.execute("INSERT OR REPLACE INTO state VALUES ('archive_done', '1')")
            db.commit()
            if not args.keep_archive and args.archive is None:
                archive.unlink(missing_ok=True)
                print("Archive processed and deleted (pass --keep-archive to keep it).", flush=True)
        state = dict(db.execute("SELECT key, value FROM state"))

    if state.get("top_up_done") != "1":
        since = datetime.fromisoformat(args.since or state["archive_date"])
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)
        processor = Processor(db, args.workers, args.max_sites, "top-up")
        process_top_up(processor, since, args.refresh_modified, args.limit)
        processor.close()
        if args.limit is None:
            db.execute("INSERT OR REPLACE INTO state VALUES ('top_up_done', '1')")
            db.execute("INSERT OR REPLACE INTO state VALUES ('cod_snapshot', ?)", (datetime.now(timezone.utc).date().isoformat(),))
            db.commit()

    counts = {s: n for s, n in db.execute("SELECT status, COUNT(*) FROM skipped GROUP BY status")}
    entries = db.execute("SELECT COUNT(*) FROM id").fetchone()[0]
    snapshot = dict(db.execute("SELECT key, value FROM state")).get("cod_snapshot", "partial")
    db.close()
    print(f"Patterns stored: {entries}; skipped: {counts.get('skip', 0)}; failed: {counts.get('fail', 0)}.", flush=True)
    build_cache(source, cache, release=f"COD-{snapshot}")
    print(
        "\nUse it with Phasentic by setting:\n"
        "  PHASENTIC_REFERENCE_SOURCE=pow_cod\n"
        f"  PHASENTIC_POWCOD_PATH={source}\n"
        f"  PHASENTIC_POWCOD_CACHE_PATH={cache}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
