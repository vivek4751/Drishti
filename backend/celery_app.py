from celery import Celery
from config import JOB_TTL, REDIS_URL, RESULT_URL
celery_app = Celery("drishti", broker=REDIS_URL, backend=RESULT_URL, include=["tasks"])
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    task_track_started=True, result_expires=JOB_TTL, task_default_queue="drishti",
    worker_prefetch_multiplier=1, broker_connection_retry_on_startup=True,
    broker_connection_timeout=3, task_publish_retry=False,
    redis_socket_connect_timeout=3, redis_socket_timeout=3,
    broker_transport_options={"socket_connect_timeout": 3, "socket_timeout": 3},
)
