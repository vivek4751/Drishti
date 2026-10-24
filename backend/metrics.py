from prometheus_client import Counter, Histogram
HTTP_TOTAL = Counter("drishti_http_requests", "API requests", ["method", "route", "status"])
HTTP_SECONDS = Histogram("drishti_http_seconds", "API latency", ["route"])
JOB_TOTAL = Counter("drishti_jobs", "Finished jobs", ["modality", "outcome"])
INFERENCE_SECONDS = Histogram(
    "drishti_inference_seconds", "Inference including first model load", ["modality"],
    buckets=(0.1, 0.5, 1, 5, 15, 30, 60, 120, 300, 600),
)
