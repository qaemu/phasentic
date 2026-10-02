"""Explicit selection of the demo subset or POW_COD."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping

from phasentic.domain.models import AnalysisSettings
from phasentic.references.demo import DemoReferenceStore
from phasentic.references.powcod import PowCodError, PowCodReferenceStore


class ReferenceConfigurationError(RuntimeError):
    """The requested reference source cannot be served by this process."""


POWCOD_DATABASE_NAME = "cod2205.sq"
POWCOD_CACHE_NAME = "powcod-2205.xrd.sqlite"


def phasentic_home(environment: Mapping[str, str] | None = None) -> Path:
    """Directory where ``phasentic setup-powcod`` installs POW_COD (``~/.phasentic``)."""

    values = environment if environment is not None else os.environ
    raw = values.get("PHASENTIC_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".phasentic"


def _installed(name: str, environment: Mapping[str, str] | None) -> Path | None:
    candidate = phasentic_home(environment) / "powcod" / name
    return candidate if candidate.is_file() else None


def default_reference_source(environment: Mapping[str, str] | None = None) -> str:
    """``PHASENTIC_REFERENCE_SOURCE`` if set, else POW_COD when installed, else the demo subset."""

    values = environment if environment is not None else os.environ
    selected = values.get("PHASENTIC_REFERENCE_SOURCE", "").strip()
    if selected in {"demo", "pow_cod"}:
        return selected
    if configured_powcod_path(environment=values) and configured_powcod_cache_path(environment=values):
        return "pow_cod"
    return "demo"


def configured_powcod_path(
    explicit_path: Path | str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    values = environment if environment is not None else os.environ
    raw = explicit_path if explicit_path is not None else values.get("PHASENTIC_POWCOD_PATH")
    if raw is None or not str(raw).strip():
        return _installed(POWCOD_DATABASE_NAME, values)
    return Path(str(raw)).expanduser()


def configured_powcod_cache_path(
    explicit_path: Path | str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    values = environment if environment is not None else os.environ
    raw = explicit_path if explicit_path is not None else values.get("PHASENTIC_POWCOD_CACHE_PATH")
    if raw is None or not str(raw).strip():
        return _installed(POWCOD_CACHE_NAME, values)
    return Path(str(raw)).expanduser()


def configured_powcod_equivalence_path(
    explicit_path: Path | str | None = None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    values = environment if environment is not None else os.environ
    raw = explicit_path if explicit_path is not None else values.get("PHASENTIC_POWCOD_EQUIVALENCE_PATH")
    if raw is None or not str(raw).strip():
        return None
    return Path(str(raw)).expanduser()


def open_reference_store(
    settings: AnalysisSettings,
    *,
    powcod_path: Path | str | None = None,
    powcod_cache_path: Path | str | None = None,
    powcod_equivalence_path: Path | str | None = None,
    environment: Mapping[str, str] | None = None,
) -> DemoReferenceStore | PowCodReferenceStore:
    """Open exactly the requested source; never fall back to another one."""

    settings.validate()
    source = settings.reference_source
    if source == "demo":
        return DemoReferenceStore()
    if source == "pow_cod":
        database = configured_powcod_path(powcod_path, environment=environment)
        if database is None:
            raise ReferenceConfigurationError(
                "POWCOD_NOT_CONFIGURED: set PHASENTIC_POWCOD_PATH to a verified POW_COD SQLite database"
            )
        cache = configured_powcod_cache_path(powcod_cache_path, environment=environment)
        equivalence = configured_powcod_equivalence_path(powcod_equivalence_path, environment=environment)
        try:
            return PowCodReferenceStore(database, cache_path=cache, equivalence_path=equivalence)
        except PowCodError:
            raise
        except Exception as exc:
            raise ReferenceConfigurationError(f"POWCOD_UNREADABLE: {database}") from exc
    raise ReferenceConfigurationError(f"REFERENCE_SOURCE_UNSUPPORTED: {source}")


def reference_source_status(*, environment: Mapping[str, str] | None = None) -> dict[str, object]:
    """Return safe UI metadata without exposing arbitrary client paths."""

    values = environment if environment is not None else os.environ
    powcod: dict[str, object] = {"available": False}
    powcod_path = configured_powcod_path(environment=values)
    if powcod_path is not None:
        powcod["configured"] = True
        try:
            store = PowCodReferenceStore(
                powcod_path,
                cache_path=configured_powcod_cache_path(environment=values),
                equivalence_path=configured_powcod_equivalence_path(environment=values),
            )
            metadata = store.metadata()
            powcod.update(
                {
                    "available": True,
                    "release": metadata.get("release"),
                    "database_sha256": metadata.get("source_sha256"),
                    "cache_sha256": metadata.get("cache_sha256"),
                    "schema_version": metadata.get("schema_version"),
                }
            )
            store.close()
        except PowCodError as exc:
            powcod["error"] = str(exc).split(":", 1)[0]
    else:
        powcod["configured"] = False
    selected = default_reference_source(values)
    return {
        "selected": selected,
        "sources": {
            "demo": {"available": True, "label": "Offline demo subset"},
            "pow_cod": {"label": "POW_COD 2205", **powcod},
        },
    }


__all__ = [
    "ReferenceConfigurationError",
    "default_reference_source",
    "phasentic_home",
    "configured_powcod_cache_path",
    "configured_powcod_equivalence_path",
    "configured_powcod_path",
    "open_reference_store",
    "reference_source_status",
]
