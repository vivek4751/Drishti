import io
import json
import subprocess
import sys
import time
from unittest.mock import Mock
import pytest
from celery.contrib.testing.worker import start_worker
from fastapi.testclient import TestClient
import main
import tasks
from celery_app import celery_app
from job_store import store

@pytest.fixture
def client(setup):
    with TestClient(main.app) as client:
        yield client

def upload(client, modality="image", name="sample.png", content=b"x" * 200):
    return client.post(f"/analyze/{modality}", files={"file": (name, io.BytesIO(content))})

def test_api_starts_without_ml_dependencies():
    result = subprocess.check_output([sys.executable, "-c",
        "import main,sys,json; print(json.dumps([m for m in ['torch','transformers','cv2','audio_detector','image_detector','document_detector'] if m in sys.modules]))"],
        cwd=str(main.Path(main.__file__).parent), text=True)
    assert json.loads(result.strip()) == []

@pytest.mark.parametrize("modality,name,content", [
    ("image", "sample.png", b"x" * 200),
    ("video", "sample.mp4", b"x" * 200),
    ("audio", "sample.wav", b"x" * 200),
    ("document", "sample.pdf", b"%PDF-" + b"x" * 200),
])
def test_completed_job_round_trip(client, monkeypatch, setup, modality, name, content):
    monkeypatch.setattr(tasks, "analyze", lambda kind, path, filename: {
        "verdict": "REAL", "confidence": 0.6, "media_type": kind, "filename": filename})
    response = upload(client, modality, name, content)
    assert response.status_code == 202
    body = response.json()
    status = client.get(body["status_url"]).json()
    assert status["status"] == "SUCCESS"
    assert status["result"]["media_type"] == modality
    assert list(setup.iterdir()) == []
    assert store.client.ttl(f"drishti:job:{body['job_id']}") > 0

def test_worker_failure_cleans_upload_and_hides_exception(client, monkeypatch, setup):
    monkeypatch.setattr(tasks, "analyze", Mock(side_effect=RuntimeError("secret model path")))
    response = upload(client)
    status = client.get(response.json()["status_url"])
    assert status.json()["status"] == "FAILURE"
    assert "secret model path" not in status.text
    assert list(setup.iterdir()) == []

def test_broker_outage_rejects_and_cleans(client, monkeypatch, setup):
    monkeypatch.setattr(main.analyze_media, "apply_async", Mock(side_effect=ConnectionError("offline")))
    assert upload(client).status_code == 503
    assert list(setup.iterdir()) == []
    assert not list(store.client.scan_iter("drishti:job:*"))

@pytest.mark.parametrize("modality,name,content,expected", [
    ("image", "bad.exe", b"x" * 200, 415),
    ("document", "bad.pdf", b"x" * 200, 400),
    ("image", "empty.png", b"", 400),
])
def test_invalid_uploads(client, setup, modality, name, content, expected):
    assert upload(client, modality, name, content).status_code == expected
    assert list(setup.iterdir()) == []

def test_size_limit_enforced_during_upload(client, monkeypatch, setup):
    monkeypatch.setitem(main.LIMIT_MB, "image", 0)
    assert upload(client).status_code == 413
    assert list(setup.iterdir()) == []

def test_unknown_and_expired_jobs_return_404(client):
    assert client.get("/jobs/" + "0" * 32).status_code == 404
    assert client.get("/jobs/not-a-job").status_code == 404
    job_id = "a" * 32
    store.create(job_id, {"modality": "image"})
    store.delete(job_id)
    assert client.get("/jobs/" + job_id).status_code == 404

def test_filename_cannot_choose_storage_path(client, monkeypatch, setup):
    monkeypatch.setattr(main.analyze_media, "apply_async", Mock())
    response = upload(client, name="../../outside.png")
    assert response.status_code == 202
    meta = store.get(response.json()["job_id"])
    assert meta["filename"] == "outside.png"
    assert list(setup.iterdir())[0].name == response.json()["job_id"] + ".png"
    assert client.get(response.json()["status_url"]).json()["status"] == "QUEUED"

def test_metrics_use_route_templates(client):
    client.get("/jobs/" + "b" * 32)
    text = client.get("/metrics").text
    assert 'route="/jobs/{job_id}"' in text
    assert "b" * 32 not in text

def test_redis_outage_readiness(client, monkeypatch):
    monkeypatch.setattr(store, "ping", Mock(side_effect=ConnectionError("offline")))
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200

def test_real_celery_worker_consumes_message(client, monkeypatch, setup):
    # Real Celery worker + serialization, in-memory broker/backend, fake Redis metadata.
    celery_app.conf.task_always_eager = False
    monkeypatch.setattr(tasks, "analyze", lambda kind, path, name: {"verdict": "REAL", "filename": name})
    with start_worker(celery_app, pool="solo", concurrency=1, perform_ping_check=False):
        response = upload(client)
        assert response.status_code == 202
        for _ in range(60):
            status = client.get(response.json()["status_url"]).json()
            if status["status"] in {"SUCCESS", "FAILURE"}:
                break
            time.sleep(0.1)
        assert status["status"] == "SUCCESS"
        assert status["result"]["filename"] == "sample.png"
    assert list(setup.iterdir()) == []
