import os
from pathlib import Path
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
RESULT_URL = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).parent / "uploads"))).resolve()
JOB_TTL = int(os.getenv("JOB_TTL_SECONDS", "86400"))
