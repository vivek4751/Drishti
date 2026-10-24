FROM python:3.11-slim AS api
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app/backend
COPY backend/requirements-api.txt ./requirements-api.txt
RUN pip install --no-cache-dir -r requirements-api.txt
COPY backend/ ./
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM api AS worker
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY backend/requirements-worker.txt ./requirements-worker.txt
RUN pip install --no-cache-dir -r requirements-worker.txt
COPY video_model_training/ /app/video_model_training/
CMD ["celery", "-A", "celery_app:celery_app", "worker", "--pool=solo", "--concurrency=1", "--loglevel=INFO"]
