import os
import sys
from pathlib import Path
os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
os.environ["WORKER_METRICS_PORT"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fakeredis
import pytest
import main
import tasks
from celery_app import celery_app
from job_store import store

@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "client", fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setattr(main, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(tasks, "UPLOAD_DIR", tmp_path)
    celery_app.conf.update(task_always_eager=True, task_store_eager_result=True,
                           task_eager_propagates=False, broker_url="memory://")
    return tmp_path
