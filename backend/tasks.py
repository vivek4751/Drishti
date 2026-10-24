import logging
import re
import time
from celery.signals import worker_init
from prometheus_client import start_http_server
from celery_app import celery_app
from config import UPLOAD_DIR
from inference import analyze
from job_store import store
from metrics import INFERENCE_SECONDS, JOB_TOTAL
logger = logging.getLogger(__name__)

@worker_init.connect
def start_metrics(**kwargs):
    import os
    port = int(os.getenv("WORKER_METRICS_PORT", "9101"))
    if port:
        # One solo process per worker container: metrics are process-local.
        start_http_server(port)

@celery_app.task(name="drishti.analyze")
def analyze_media(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        raise ValueError("Invalid job ID")
    metadata = store.get(job_id)
    if metadata is None:
        raise ValueError("Job metadata expired")
    modality, extension = metadata["modality"], metadata["extension"]
    if modality not in {"image", "video", "audio", "document"} or not re.fullmatch(r"\.[a-z0-9]+", extension):
        raise ValueError("Invalid job metadata")
    path = UPLOAD_DIR / f"{job_id}{extension}"
    started, outcome = time.perf_counter(), "failure"
    try:
        result = analyze(modality, path, metadata["filename"])
        outcome = "success"
        return result
    except Exception:
        logger.exception("Analysis failed for job %s", job_id)
        raise
    finally:
        INFERENCE_SECONDS.labels(modality).observe(time.perf_counter() - started)
        JOB_TOTAL.labels(modality, outcome).inc()
        path.unlink(missing_ok=True)
