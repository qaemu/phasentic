import asyncio
import hashlib
import hmac
import tempfile
import json
import multiprocessing
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Callable

from phasentic import __version__
from phasentic.acquisition.calibration import calibrate_standard_file
from phasentic.api.contracts import settings_from_payload
from phasentic.domain.models import CalibrationResult
from phasentic.importers import ImportErrorDetail
from phasentic.references.factory import ReferenceConfigurationError, default_reference_source, reference_source_status
from phasentic.references.powcod import PowCodError
from phasentic.reporting.service import analyze_file
from phasentic.search.mixtures import MIXTURE_ALGORITHM_VERSION

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


# Jobs run in a separate worker process (see ``_isolated``). They are
# module-level so the spawned worker can import them, and they return
# ``(status_code, body)`` instead of raising so the HTTP error text is the same
# as when the work ran inside the server.
def _calibration_job(path: Path, standard_id: str, radiation: str) -> tuple[int, Any]:
    try:
        return 200, calibrate_standard_file(path, standard_id, radiation).to_dict()
    except (ImportErrorDetail, RuntimeError, ValueError) as exc:
        return 400, str(exc)


def _analysis_job(path: Path, settings: Any, original_name: str) -> tuple[int, Any]:
    try:
        report = analyze_file(
            path,
            settings,
            powcod_path=os.environ.get("PHASENTIC_POWCOD_PATH"),
            powcod_cache_path=os.environ.get("PHASENTIC_POWCOD_CACHE_PATH"),
            powcod_equivalence_path=os.environ.get("PHASENTIC_POWCOD_EQUIVALENCE_PATH"),
            original_filename=original_name,
        )
        return 200, report.to_dict()
    except ImportErrorDetail as exc:
        return 400, str(exc)
    except (ReferenceConfigurationError, PowCodError) as exc:
        return 400, str(exc).split(":", 1)[0]
    except (TypeError, AttributeError, OSError):
        return 400, "The uploaded pattern could not be processed"
    except ValueError as exc:
        return 400, str(exc)


def _exit_with_parent() -> None:
    # The server enforces the time limit; if it dies (kill -9, crash) nobody
    # would stop this worker, so it stops itself.
    multiprocessing.parent_process().join()
    os._exit(1)


def _run_job(sender: Any, job: Callable[..., tuple[int, Any]], args: tuple[Any, ...]) -> None:
    threading.Thread(target=_exit_with_parent, daemon=True).start()
    try:
        outcome = job(*args)
    except Exception:  # anything unexpected stays a generic server error, as before
        outcome = (500, "Internal error while processing the scan")
    sender.send(outcome)
    sender.close()


def _calibration_signature(key: bytes, payload: dict[str, Any]) -> str:
    # Sign the normalized form, so a browser JSON round trip (1.0 -> 1) still verifies.
    canonical = json.dumps(CalibrationResult.from_dict(payload).to_dict(), sort_keys=True, separators=(",", ":"))
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def create_app() -> Any:
    """Create the FastAPI app lazily so scientific CLI use needs no web stack."""

    try:
        from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
        from fastapi.responses import FileResponse, PlainTextResponse
        from fastapi.staticfiles import StaticFiles
        from starlette.concurrency import run_in_threadpool
        from starlette.datastructures import MutableHeaders
    except ImportError as exc:
        raise RuntimeError(
            "The web interface needs FastAPI; reinstall Phasentic: pip install --force-reinstall phasentic"
        ) from exc

    # The interactive API docs load scripts from a CDN, which the page CSP
    # blocks, so they are not served.
    app = FastAPI(title="Phasentic", version=__version__, docs_url=None, redoc_url=None)
    # A host name other than loopback only arrives through DNS rebinding,
    # unless `phasentic serve --host` named it explicitly.
    allowed_hosts = LOOPBACK_HOSTS | {os.environ.get("PHASENTIC_BIND_HOST", "127.0.0.1")}
    timeout_seconds = float(os.environ.get("PHASENTIC_ANALYSIS_TIMEOUT_SECONDS", "300"))
    # ponytail: per-process key; calibrations from before a server restart must be redone.
    calibration_key = secrets.token_bytes(32)
    # ponytail: one heavy job at a time for a single local user; a queue if a server is ever shared.
    job_lock = asyncio.Lock()

    class RequestGuard:
        """Host/Origin checks and security headers as plain ASGI middleware.

        ``@app.middleware("http")`` would hide client disconnects from the
        endpoints, and ``_isolated`` needs them to stop abandoned work.
        """

        def __init__(self, inner: Any) -> None:
            self.inner = inner

        async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
            if scope["type"] != "http":
                await self.inner(scope, receive, send)
                return

            async def send_with_headers(message: Any) -> None:
                if message["type"] == "http.response.start":
                    headers = MutableHeaders(scope=message)
                    headers["X-Content-Type-Options"] = "nosniff"
                    headers["X-Frame-Options"] = "DENY"
                    headers["Referrer-Policy"] = "no-referrer"
                    headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'"
                await send(message)

            request = Request(scope)
            origin = request.headers.get("origin")
            if request.url.hostname not in allowed_hosts:
                await PlainTextResponse("Host not allowed", status_code=400)(scope, receive, send_with_headers)
            elif request.method != "GET" and origin is not None and origin != f"{request.url.scheme}://{request.url.netloc}":
                # Browsers always send Origin on cross-site POSTs; scripts and the CLI send none.
                await PlainTextResponse("Cross-origin requests are not accepted", status_code=403)(
                    scope, receive, send_with_headers
                )
            else:
                await self.inner(scope, receive, send_with_headers)

    app.add_middleware(RequestGuard)

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

    def _verified_calibration(raw: dict[str, Any]) -> dict[str, Any]:
        calibration = dict(raw)
        signature = calibration.pop("signature", None)
        try:
            expected = _calibration_signature(calibration_key, calibration)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Calibration result is invalid") from exc
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            raise HTTPException(
                status_code=400,
                detail="This calibration was not issued by this server; calibrate the standard scan again",
            )
        return calibration

    async def _isolated(request: Any, job: Callable[..., tuple[int, Any]], *args: Any) -> Any:
        """Run a job in a worker process that is killed on timeout or client disconnect.

        A thread cannot be stopped, so a heavy request used to run to completion
        after its client had gone. The worker is spawned (not forked) to stay
        safe next to the server's threads; startup costs well under a second.
        """

        if job_lock.locked():
            raise HTTPException(status_code=429, detail="Another analysis is still running; wait for it to finish")
        async with job_lock:
            context = multiprocessing.get_context("spawn")
            receiver, sender = context.Pipe(duplex=False)
            worker = context.Process(target=_run_job, args=(sender, job, args), daemon=True)
            worker.start()
            sender.close()
            deadline = time.monotonic() + timeout_seconds
            try:
                # poll() also turns true when the worker dies, and recv() then raises EOFError.
                while not receiver.poll():
                    if time.monotonic() > deadline:
                        raise HTTPException(
                            status_code=503,
                            detail=f"The analysis was stopped after {timeout_seconds:g} s; use smaller search settings",
                        )
                    if await request.is_disconnected():
                        raise HTTPException(status_code=400, detail="The request was cancelled")
                    await asyncio.sleep(0.2)
                status, body = await run_in_threadpool(receiver.recv)
            except EOFError as exc:
                raise HTTPException(status_code=500, detail="The analysis worker stopped unexpectedly") from exc
            finally:
                receiver.close()
                if worker.is_alive():
                    worker.kill()
                await run_in_threadpool(worker.join)
        if status != 200:
            raise HTTPException(status_code=status, detail=body)
        return body

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
        request: Request,
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
            result = await _isolated(request, _calibration_job, temporary_path, standard_id.strip(), radiation.strip())
            # The browser sends this back with each analysis; the signature
            # proves the server produced it, so a hand-edited "passed" result
            # cannot unlock a supported decision.
            result["signature"] = _calibration_signature(calibration_key, result)
            return {"success": True, "data": result}
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
            await file.close()

    @app.post("/api/v1/analyze")
    async def analyze(
        request: Request,
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
        if "calibration" in payload:
            if calibration_payload:
                raise HTTPException(status_code=400, detail="Provide calibration in one request field only")
            calibration_payload = payload.pop("calibration") or {}
            if not isinstance(calibration_payload, dict):
                raise HTTPException(status_code=400, detail="calibration must be a JSON object")
        if calibration_payload:
            payload["calibration"] = _verified_calibration(calibration_payload)
        try:
            settings = settings_from_payload(payload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        temporary_path: Path | None = None
        try:
            temporary_path, original_name = await _save_upload(file, suffix)
            report = await _isolated(request, _analysis_job, temporary_path, settings, original_name)
            return {"success": True, "data": report}
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
