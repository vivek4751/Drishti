# Drishti: local deepfake detection prototype

This version adds Celery, Redis and Prometheus to the supplied project. It has not been deployed. ONNX Runtime and MLflow have not been implemented. These additions do not establish detection accuracy or lower the memory required by a loaded neural model.

## What changed

- FastAPI starts without importing PyTorch, Transformers, OpenCV or detector modules.
- Image/video/audio/document uploads return HTTP 202 with a job ID. The React screens poll until the worker returns a result or failure.
- Celery executes inference separately. Redis database 0 holds broker messages and job metadata; database 1 holds Celery results. Metadata/results expire after 24 hours by default.
- Uploads live on shared storage, not inside Redis messages. The worker deletes uploads after success or failure. If the worker crashes or a message expires, stop the stack and run the cleanup command below.
- `/metrics` exposes API request counts/latency. The worker exposes job success/failure counts and inference latency on port 9101. Model initialization is included in the first inference duration.
- The incomplete image detector was replaced with an actual pretrained Swin classifier adapter. Its labels come from the model configuration. The old image UI's unsupported FFT/face/heatmap panels were removed.
- Missing audio/video models now fail instead of producing mock/random predictions. Video score inflation was removed, the exact-15-frame sampling boundary was fixed, and GPU inference batches default to one segment.
- Training AMP calls were aligned with the original pinned PyTorch version. Training itself was not run.
- Legacy image/document route files and WAHA helpers remain in the source archive but are not registered by the new main app. Reports use the shared report generator. The WhatsApp integration is not enabled or verified.

## Architecture

Browser -> POST /analyze/{image|video|audio|document} -> shared upload + Redis metadata -> Celery worker -> detector -> Redis result -> GET /jobs/{job_id} -> browser.

API and worker must see the same UPLOAD_DIR. The Compose volume provides this on one Docker host. Separate machines need shared storage or an object-storage implementation; local paths are insufficient.

## Run locally with Docker Desktop (Linux containers)

Docker was not available in the authoring environment, so the Compose build/run is provided but unverified. Celery does not officially support native Windows; use Linux containers or WSL2 for the full stack.

1. In this directory, run `docker compose up --build`.
2. API documentation: http://127.0.0.1:8000/docs. Liveness: `/health`; `/ready` checks Redis connectivity only, not worker/model readiness.
3. For monitoring, run `docker compose --profile monitoring up --build`. Open http://127.0.0.1:9090 and check Targets. Useful query: `rate(drishti_jobs_total[5m])`; inference latency: `rate(drishti_inference_seconds_sum[5m]) / rate(drishti_inference_seconds_count[5m])`.
4. In frontend/, copy `.env.example` to `.env`, supply your Auth0 domain/client ID, run `npm ci`, then `npm run dev`. Configure Auth0 allowed callback/logout/web origins for http://localhost:5173. Auth0 values are not supplied in the original archive.
5. Submit a file through the UI or `/docs`. Example with PowerShell: `curl.exe -F "file=@sample.png" http://127.0.0.1:8000/analyze/image`. Poll the returned `status_url`.
6. For old abandoned uploads, stop API/worker, then run `docker compose run --rm --no-deps api python cleanup_uploads.py`. Do not clean uploads while inference is running.
7. Stop with `docker compose down`. Named upload/model/Redis volumes persist; this does not delete them.

The API can run with only `pip install -r backend/requirements-api.txt`; a functioning analysis stack still needs Redis, a worker with requirements-worker.txt, and model assets. The separate API requirements do not include torch.

## Models and limitations

- Image: `Organika/sdxl-detector`, a pretrained Swin image classifier. First use downloads weights. Its model card limits it to noncommercial use and warns of generator-domain sensitivity. Its scores are not calibrated certainty, and it does not prove image authenticity.
- Audio: pretrained `MelodyMachine/Deepfake-audio-detection-V2`, or a local model under backend/models/niriksha-audio-v1. FFmpeg decodes audio; inference combines neural output and heuristic signal checks. No measured accuracy is supplied. Loading failure is an analysis failure.
- Video: supply your trained `video_model_training/video_deepfake_model.pth`. It is absent from the original ZIP. EfficientNet-B4 features feed an LSTM over 15 frames. At most 40 sampled segments are considered. The maximum fake score selects the verdict at 0.5. GPU batch size is configurable with VIDEO_INFERENCE_BATCH_SIZE; CPU memory still holds sampled face tensors.
- The video training pipeline samples frames across a video, while inference uses consecutive frame blocks. Align these before retraining/evaluating temporal performance. Random video splits do not guarantee disjoint identities or source families.
- Document: heuristic PDF screening across metadata, structure, recompression patterns, text and signature indicators. A REAL verdict means no sufficiently strong indicators under these rules; it does not establish authenticity. Signature indicator checks are not cryptographic signature validation.
- Grad-CAM visualizes model sensitivity, not ground-truth manipulated pixels. Neither hashes nor generated PDF reports certify authenticity. Reports contain user-supplied results and are not signed audit records.
- No model weights were downloaded and no inference/training, accuracy, latency benchmark or cloud deployment was validated during this update.

## Operational scope

This remains a localhost prototype. Compose binds API/Prometheus to loopback and leaves Redis unexposed. Auth0 currently gates only the frontend; the API does not validate access tokens. Add API authentication, user-owned jobs, quotas, transport limits, and retention policies before public hosting.

Use one API process and one solo worker process for this metrics configuration. Solo workers do not enforce Celery hard time limits. A stuck native model call needs operator intervention. Tasks are acknowledged before execution and do not automatically retry; a worker crash can leave a job pending/started until expiry. Restart/recovery policies and durable job reconciliation remain future work. Increasing worker replicas duplicates model memory and requires per-worker Prometheus targets.

Extension validation and PDF header checks reject obvious invalid inputs; actual image/audio/video decoding occurs in the worker. Request upload byte limits do not replace a reverse-proxy body limit. Job IDs are random bearer identifiers, not authorization. The frontend waits up to 15 minutes; a timeout stops polling and does not cancel inference.

ONNX is deferred until a checkpoint can be exported and compared with PyTorch on representative inputs. MLflow is deferred until actual training/evaluation runs produce metrics worth recording. Do not list either as used in the resume.

## Validation

From backend/: `python -m pip install -r requirements-test.txt` then `python -m pytest tests -q`.
From frontend/: `npm ci`, `npm test`, `npm run build`.

Backend tests use fake Redis metadata, an in-memory Celery result backend, and both eager execution and a real Celery solo worker with in-memory transport. Detector execution is substituted to test orchestration without downloading models. Missing-model regression tests execute the relevant functions in isolation. These checks do not validate an actual Redis service, Docker networking, real model predictions, Auth0 login, or the rendered browser experience.

Official references:
- https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html
- https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows
- https://prometheus.github.io/client_python/exporting/http/asgi/
- https://huggingface.co/Organika/sdxl-detector
- https://huggingface.co/Organika/sdxl-detector/raw/main/config.json
