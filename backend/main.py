"""Accept uploads and expose job status without loading inference models."""

import io
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from celery_app import celery_app
from config import JOB_TTL, UPLOAD_DIR
from job_store import store
from metrics import HTTP_SECONDS, HTTP_TOTAL
from tasks import analyze_media

logger = logging.getLogger(__name__)

Modality = Literal["image", "video", "audio", "document"]
EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"},
    "video": {".mp4", ".webm", ".mov", ".mkv"},
    "audio": {".mp3", ".wav", ".ogg", ".aac", ".m4a", ".flac"},
    "document": {".pdf"},
}
LIMIT_MB = {"image": 20, "video": 100, "audio": 50, "document": 50}

app = FastAPI(title="Drishti Deepfake API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def instrument(request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        # Keep job IDs out of metric labels so each job does not create a series.
        route = getattr(request.scope.get("route"), "path", "unmatched")
        if route != "/metrics":
            HTTP_TOTAL.labels(request.method, route, str(status)).inc()
            HTTP_SECONDS.labels(route).observe(time.perf_counter() - started)


@app.get("/")
@app.get("/health")
def health():
    return {"status": "ok", "service": "drishti-api", "inference": "celery-worker"}


@app.get("/ready")
def ready():
    try:
        store.ping()
    except Exception:
        raise HTTPException(503, "Redis unavailable")
    return {"status": "ok", "note": "Redis reachable; model readiness is checked per job."}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), headers={"Content-Type": CONTENT_TYPE_LATEST})


async def _write_upload(file: UploadFile, path: Path, limit_mb: int) -> int:
    size = 0
    with path.open("xb") as target:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit_mb * 1024 * 1024:
                raise HTTPException(413, "Upload exceeds the size limit")
            await run_in_threadpool(target.write, chunk)
    if size < 100:
        raise HTTPException(400, "File is empty or too small")
    return size


def _enqueue_job(job_id: str, metadata: dict):
    store.create(job_id, metadata)
    analyze_media.apply_async(args=[job_id], task_id=job_id, expires=JOB_TTL)


@app.post("/analyze/{modality}", status_code=202)
@app.post("/jobs/{modality}", status_code=202)
async def submit(modality: Modality, file: UploadFile = File(...)):
    filename = (file.filename or "").replace("\\", "/").split("/")[-1][:200]
    extension = Path(filename).suffix.lower()
    if extension not in EXTENSIONS[modality]:
        raise HTTPException(415, f"Unsupported file extension for {modality}")

    job_id = uuid.uuid4().hex
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{job_id}{extension}"
    submitted = False
    try:
        size = await _write_upload(file, path, LIMIT_MB[modality])
        if modality == "document":
            with path.open("rb") as source:
                if source.read(5) != b"%PDF-":
                    raise HTTPException(400, "Invalid PDF header")

        metadata = {
            "modality": modality,
            "filename": filename,
            "extension": extension,
            "size_bytes": size,
        }
        await run_in_threadpool(_enqueue_job, job_id, metadata)
        submitted = True
    except HTTPException:
        raise
    except Exception:
        logger.exception("Unable to submit analysis job")
        raise HTTPException(503, "Job service unavailable; please try again")
    finally:
        await file.close()
        # Once published, the worker owns the upload and removes it after analysis.
        if not submitted:
            path.unlink(missing_ok=True)
            try:
                await run_in_threadpool(store.delete, job_id)
            except Exception:
                logger.exception("Unable to remove unsubmitted job metadata")

    return {"job_id": job_id, "status": "QUEUED", "status_url": f"/jobs/{job_id}"}


@app.get("/jobs/{job_id}")
def job_status(job_id: str):
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise HTTPException(404, "Job not found or expired")
    try:
        metadata = store.get(job_id)
        if metadata is None:
            raise HTTPException(404, "Job not found or expired")

        task = celery_app.AsyncResult(job_id)
        state = task.state
        body = {"job_id": job_id, "status": "QUEUED" if state == "PENDING" else state}
        if state == "SUCCESS":
            body["result"] = task.result
        elif state in {"FAILURE", "REVOKED"}:
            body["error"] = "Analysis failed. Check worker logs and model availability."
        return body
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Job service unavailable")


class ReportRequest(BaseModel):
    result: dict


@app.post("/analyze/{modality}/report")
def report(modality: Modality, request: ReportRequest):
    from utils.report_generator import generate_report

    pdf = generate_report(request.result, modality)
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=Drishti_Report.pdf"},
    )


@app.post("/generate/report")
def generic_report(result: dict):
    return report(result.get("media_type", "video"), ReportRequest(result=result))
