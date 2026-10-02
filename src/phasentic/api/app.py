import tempfile
import json
import os
from pathlib import Path
from typing import Any

from phasentic import __version__
from phasentic.acquisition.calibration import calibrate_standard_file
from phasentic.api.contracts import settings_from_payload
from phasentic.importers import ImportErrorDetail
from phasentic.references.factory import ReferenceConfigurationError, default_reference_source, reference_source_status
from phasentic.references.powcod import PowCodError
from phasentic.reporting.service import analyze_file
from phasentic.search.mixtures import MIXTURE_ALGORITHM_VERSION


def create_app() -> Any:
    """Create the FastAPI app lazily so scientific CLI use needs no web stack."""

    try:
        from fastapi import FastAPI, File, Form, HTTPException, UploadFile
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles
        from starlette.concurrency import run_in_threadpool
    except ImportError as exc:
        raise RuntimeError(
            "The web interface needs FastAPI; reinstall Phasentic: pip install --force-reinstall phasentic"
        ) from exc

    app = FastAPI(title="Phasentic", version=__version__, docs_url="/api/docs")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def security_headers(request: Any, call_next: Any) -> Any:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'"
        return response

    async def _save_upload(file: Any, suffix: str) -> tuple[Path, str]:
        original_name = Path(file.filename or "pattern").name
        with tempfile.NamedTemporaryFile(prefix="xrd-upload-", suffix=suffix, delete=False) as stream:
            temporary_path = Path(stream.name)
            total = 0
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > 10 * 1024 * 1024:
                    temporary_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="The uploaded file exceeds the 10 MiB limit")
                stream.write(chunk)
        return temporary_path, original_name

    def _json_object(raw: str, field_name: str) -> dict[str, Any]:
        if len(raw) > 16_384:
            raise HTTPException(status_code=413, detail=f"{field_name} is too large")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"{field_name} must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object")
        return payload

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/v1/reference-sources")
    async def reference_sources() -> dict[str, Any]:
        return {"success": True, "data": reference_source_status(environment=os.environ)}

    @app.get("/api/v1/capabilities")
    async def capabilities() -> dict[str, Any]:
        return {
            "success": True,
            "data": {
                "mixture_screening": {
                    "available": True,
                    "algorithm_version": MIXTURE_ALGORITHM_VERSION,
                    "mode": "deterministic_nonnegative_profile_screening",
                    "quantitative_phase_fractions": False,
                },
            },
        }

    @app.post("/api/v1/calibrate")
    async def calibrate(
        file: UploadFile = File(...),
        standard_id: str = Form("silicon_srm_640g"),
        radiation: str = Form("Cu Ka"),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xy", ".xrdml", ".raw"}:
            raise HTTPException(status_code=400, detail="Unsupported file extension; use .xy, .xrdml, or .raw")
        temporary_path: Path | None = None
        try:
            temporary_path, _ = await _save_upload(file, suffix)
            # Heavy CPU work runs in a worker thread so the event loop keeps
            # serving health checks and other requests.
            result = await run_in_threadpool(
                calibrate_standard_file, temporary_path, standard_id.strip(), radiation.strip()
            )
            return {"success": True, "data": result.to_dict()}
        except (ImportErrorDetail, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            await file.close()

    @app.post("/api/v1/analyze")
    async def analyze(
        file: UploadFile = File(...),
        settings_json: str = Form("{}"),
        calibration_json: str = Form("{}"),
    ) -> dict[str, Any]:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".xy", ".xrdml", ".raw"}:
            raise HTTPException(status_code=400, detail="Unsupported file extension; use .xy, .xrdml, or .raw")
        payload = _json_object(settings_json, "Analysis settings")
        if "reference_source" not in payload:
            payload["reference_source"] = default_reference_source()
        calibration_payload = _json_object(calibration_json, "Calibration result")
        if calibration_payload:
            if "calibration" in payload:
                raise HTTPException(status_code=400, detail="Provide calibration in one request field only")
            payload["calibration"] = calibration_payload
        try:
            settings = settings_from_payload(payload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        temporary_path: Path | None = None
        try:
            temporary_path, original_name = await _save_upload(file, suffix)
            report = await run_in_threadpool(
                analyze_file,
                temporary_path,
                settings,
                powcod_path=os.environ.get("PHASENTIC_POWCOD_PATH"),
                powcod_cache_path=os.environ.get("PHASENTIC_POWCOD_CACHE_PATH"),
                powcod_equivalence_path=os.environ.get("PHASENTIC_POWCOD_EQUIVALENCE_PATH"),
                original_filename=original_name,
            )
            return {"success": True, "data": report.to_dict()}
        except ImportErrorDetail as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ReferenceConfigurationError, PowCodError) as exc:
            raise HTTPException(status_code=400, detail=str(exc).split(":", 1)[0]) from exc
        except (TypeError, AttributeError, OSError) as exc:
            raise HTTPException(status_code=400, detail="The uploaded pattern could not be processed") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            await file.close()

    frontend = Path(__file__).resolve().parents[1] / "web"
    if frontend.is_dir():
        app.mount("/static", StaticFiles(directory=frontend), name="static")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(frontend / "index.html")

    return app
