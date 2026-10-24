# Drishti

Drishti is a local prototype for screening images, videos, audio and PDFs for signs of AI generation or manipulation. The React app accepts uploads and displays a verdict, score and downloadable report. Each media type has its own analysis pipeline.

FastAPI handles uploads and job status. A separate Celery worker runs inference, with Redis carrying jobs and storing results. This keeps model loading out of the web process. The worker still needs enough memory for the models it loads.

## Run locally

Use Docker Desktop with Linux containers, or run the services under WSL2. Celery does not officially support native Windows. You also need Node.js and an Auth0 application for the frontend.

Before testing video analysis, place a trained checkpoint at `video_model_training/video_deepfake_model.pth`. The repository does not include one. Image and audio models download on first use unless local weights are available.

Start the API, Redis and worker from the repository root:

```sh
docker compose up --build
```

Open [the API docs](http://127.0.0.1:8000/docs) to submit a file without using the frontend. `/health` checks that the API is running; `/ready` checks Redis connectivity. Neither endpoint verifies that the worker or models are ready.

For the frontend:

1. Copy `frontend/.env.example` to `frontend/.env`.
2. Set `VITE_AUTH0_DOMAIN` and `VITE_AUTH0_CLIENT_ID` to your Auth0 application values.
3. Add `http://localhost:5173` to the application's allowed callback URLs, logout URLs and web origins.
4. Run the following commands:

```sh
cd frontend
npm ci
npm run dev
```

`VITE_API_BASE` defaults to `http://127.0.0.1:8000`.

To submit an image from PowerShell:

```powershell
curl.exe -F "file=@sample.png" http://127.0.0.1:8000/analyze/image
```

The response contains a `job_id` and `status_url`. Request that URL to check progress and retrieve the result. The upload response uses HTTP 202 because inference runs separately.

Stop the stack with `docker compose down`. Redis data, uploaded files and cached models remain in named volumes. To remove uploads abandoned by a stopped worker, stop the API and worker first, then run:

```sh
docker compose run --rm --no-deps api python cleanup_uploads.py
```

Cleanup removes files older than the job retention period. Run it while inference is stopped so it does not remove an active job's input.

## How a request moves through the system

1. FastAPI checks the file extension and upload size. PDFs also need a valid header.
2. The API writes the upload to shared storage under a generated job ID, stores metadata in Redis and sends the ID to Celery.
3. The worker loads the appropriate detector, processes the file and stores the result in Redis.
4. The frontend polls `/jobs/{job_id}` until the task completes or fails.
5. The worker removes the uploaded file after success or failure. A crash can leave it behind for the cleanup command.

Redis database 0 holds broker messages and job metadata. Database 1 holds Celery results. Metadata and results expire after 24 hours by default; media bytes stay in shared storage rather than broker messages.

The API and worker must see the same `UPLOAD_DIR`. Compose provides a shared volume on one Docker host. Workers on separate machines need shared storage or an object-storage implementation.

The active API uses the shared PDF report generator. The older image/document route modules and WAHA helpers remain in the repository but are not registered; the WhatsApp integration is disabled and unverified.

## Models and scoring

| Input | Pipeline | Limits |
| --- | --- | --- |
| Image | Pretrained `Organika/sdxl-detector`, a Swin classifier. Class indices come from its label map. | The model is intended for noncommercial use and may perform differently on other image generators. Its score does not prove authenticity or locate an edit. |
| Audio | Pretrained `MelodyMachine/Deepfake-audio-detection-V2`, or local weights in `backend/models/niriksha-audio-v1`. FFmpeg decodes audio before neural and signal-based checks. | The combined score includes heuristics. No project-level accuracy result has been established. |
| Video | MTCNN face crops, EfficientNet-B4 features and an LSTM over 15 frames. | Up to 40 sampled segments are classified. A maximum fake score of at least 0.5 produces a FAKE verdict; this can miss unsampled edits or flag an otherwise genuine video. |
| PDF | PyMuPDF checks metadata, structure, image recompression patterns, text and signature indicators. | These are screening rules. A REAL verdict means the rules did not find strong enough indicators; signature checks do not perform cryptographic validation. |

Missing audio or video models fail the job. The application does not substitute random or untrained predictions. Video GPU inference defaults to one segment per batch; sampled face tensors still occupy CPU memory.

Video training samples frames across a video, while inference uses consecutive blocks. Align the sampling before retraining and evaluating temporal performance. The random video split also does not guarantee separate identities or source families across training and validation.

Scores are not calibrated certainty. Grad-CAM shows model sensitivity rather than verified manipulated pixels. File hashes identify bytes; neither hashes nor PDF reports certify authenticity. Reports use client-supplied results and are not signed audit records.

## Monitoring

Start Prometheus with the optional monitoring profile:

```sh
docker compose --profile monitoring up --build
```

Open [Prometheus](http://127.0.0.1:9090) and check its Targets page. The API exposes request counts and latency at `/metrics`. Worker metrics on port 9101 track completed jobs, failures and inference duration. The first job's duration includes model loading.

Job completion rate:

```promql
rate(drishti_jobs_total[5m])
```

Mean inference duration over five minutes:

```promql
rate(drishti_inference_seconds_sum[5m]) / rate(drishti_inference_seconds_count[5m])
```

Use one API process and one solo worker process with this metrics setup. Each additional worker loads its own models and needs its own Prometheus scrape target.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Broker and job metadata. Compose uses the `redis` service hostname. |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/1` | Celery task results. |
| `UPLOAD_DIR` | `backend/uploads` | Shared upload directory. Compose uses `/data/uploads`. |
| `JOB_TTL_SECONDS` | `86400` | Job metadata/result retention and abandoned-upload cleanup age. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Allowed frontend origins. |
| `IMAGE_MODEL` | `Organika/sdxl-detector` | Image model ID or local model path. |
| `VIDEO_MODEL_PATH` | `video_model_training/video_deepfake_model.pth` | Trained video checkpoint, resolved relative to the project by default. |
| `VIDEO_INFERENCE_BATCH_SIZE` | `1` | Segments per inference batch. |
| `WORKER_METRICS_PORT` | `9101` | Worker metrics endpoint; set to `0` to disable it. |

The API can run with `pip install -r backend/requirements-api.txt`, which does not install PyTorch. Processing uploads still requires Redis, model assets and a worker installed with `backend/requirements-worker.txt`. Training uses AMP calls compatible with the pinned PyTorch version, but training has not been run as part of the validation below.

## Tests

From `backend/`:

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests -q
```

From `frontend/`:

```sh
npm ci
npm test
npm run build
```

The backend tests exercise job submission, polling, failure handling, validation and upload cleanup. They use fake Redis metadata, an in-memory result backend, eager tasks and a real Celery solo worker with in-memory transport. Detector calls are substituted, and missing-model paths are tested in isolation. The frontend tests cover polling success, worker errors, HTTP errors and invalid job IDs.

These checks do not validate a Redis service, Docker networking, Auth0 login or the rendered browser flow. No model weights were downloaded for this validation; model inference, training, accuracy, latency benchmarks and a full hosted deployment remain unverified. Python syntax, Compose/Prometheus YAML parsing and the frontend production build were checked.

## Before public hosting

Compose binds the API and Prometheus to localhost and leaves Redis unexposed. Auth0 currently gates the frontend only; the API does not validate tokens or assign jobs to users. Add API authentication, job ownership, quotas, proxy body limits and retention policies before exposing the service.

The worker acknowledges tasks before execution and has no automatic retries or durable crash recovery. A crash can leave a job pending or started until expiry. Solo workers do not enforce Celery hard time limits, so a stuck native model call needs operator intervention. The frontend stops polling after 15 minutes; that does not cancel the job.

File extensions and the PDF header are early checks. Image, audio and video decoding happens in the worker. Upload size checks do not replace proxy limits, and random job IDs do not replace authorization.

ONNX Runtime and MLflow are not implemented. An ONNX export needs a checkpoint and prediction/performance comparisons against PyTorch; experiment tracking becomes useful once training and evaluation produce runs to compare.

## References

- [Celery with Redis](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
- [Celery Windows support](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows)
- [Prometheus ASGI integration](https://prometheus.github.io/client_python/exporting/http/asgi/)
- [Image model card](https://huggingface.co/Organika/sdxl-detector)
- [Image model architecture and labels](https://huggingface.co/Organika/sdxl-detector/raw/main/config.json)
