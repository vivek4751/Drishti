import json
from functools import cached_property
from redis import Redis
from config import JOB_TTL, REDIS_URL

class JobStore:
    @cached_property
    def client(self):
        return Redis.from_url(REDIS_URL, decode_responses=True,
                              socket_connect_timeout=3, socket_timeout=3)
    def ping(self):
        return self.client.ping()
    def create(self, job_id, metadata):
        self.client.set(f"drishti:job:{job_id}", json.dumps(metadata), ex=JOB_TTL)
    def get(self, job_id):
        data = self.client.get(f"drishti:job:{job_id}")
        return json.loads(data) if data else None
    def delete(self, job_id):
        self.client.delete(f"drishti:job:{job_id}")
store = JobStore()
