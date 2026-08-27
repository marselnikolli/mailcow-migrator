import redis
import json
from typing import Optional, Dict, Any
from app.config import settings
import uuid

class RedisQueue:
    def __init__(self, lock_timeout: int = 3600):
        self.redis_client = redis.from_url(settings.REDIS_URL)
        self.queue_key = "mailcow:jobs:queue"
        self.scan_queue_key = "mailcow:jobs:scan"
        self.processing_key = "mailcow:jobs:processing"
        self.lock_timeout = lock_timeout

    def push_job(self, job: Dict[str, Any]) -> str:
        """Push a job to the queue."""
        job_id = str(uuid.uuid4())
        job["job_id"] = job_id
        job_json = json.dumps(job)
        self.redis_client.lpush(self.queue_key, job_json)
        return job_id

    def pop_job(self) -> Optional[Dict[str, Any]]:
        """Pop a job from the queue (atomic RPOP)."""
        job_json = self.redis_client.rpop(self.queue_key)
        if not job_json:
            return None
        return json.loads(job_json)

    def push_scan(self, job: Dict[str, Any]) -> str:
        """Push a pre-migration scan task. Scans share the same payload shape
        as migration jobs (so the scan executor can reuse the same fields)."""
        job_id = str(uuid.uuid4())
        job["job_id"] = job_id
        self.redis_client.lpush(self.scan_queue_key, json.dumps(job))
        return job_id

    def pop_scan(self) -> Optional[Dict[str, Any]]:
        """Pop a scan task from the scan queue (atomic RPOP)."""
        job_json = self.redis_client.rpop(self.scan_queue_key)
        if not job_json:
            return None
        return json.loads(job_json)

    def get_scan_size(self) -> int:
        return self.redis_client.llen(self.scan_queue_key)
    
    def acquire_job_lock(self, job_id: str, timeout: int = 3600) -> bool:
        """Try to acquire lock on job. Uses the instance lock_timeout when the
        caller does not pass an explicit timeout."""
        lock_key = f"mailcow:lock:{job_id}"
        return bool(self.redis_client.setex(lock_key, timeout or self.lock_timeout, "1"))
    
    def release_job_lock(self, job_id: str) -> None:
        """Release lock on job."""
        lock_key = f"mailcow:lock:{job_id}"
        self.redis_client.delete(lock_key)
    
    def is_job_locked(self, job_id: str) -> bool:
        """Check if job is locked."""
        lock_key = f"mailcow:lock:{job_id}"
        return bool(self.redis_client.get(lock_key))
    
    def get_queue_size(self) -> int:
        """Get number of jobs in queue."""
        return self.redis_client.llen(self.queue_key)

    def remove_job(self, job_id: int) -> bool:
        """Remove a not-yet-started job from the queue (e.g. on cancel/delete/edit).

        Returns True if a matching entry was found and removed, False if the
        job wasn't in the queue anymore (already popped by a worker, or never
        queued)."""
        removed = False
        for job_json in self.redis_client.lrange(self.queue_key, 0, -1):
            job = json.loads(job_json)
            if job.get("id") == job_id:
                self.redis_client.lrem(self.queue_key, 1, job_json)
                removed = True
        return removed

    def request_cancel(self, job_id: int) -> None:
        """Flag a running job for cancellation; the worker checks this
        periodically and stops the transfer if it's set."""
        self.redis_client.setex(f"mailcow:cancel:{job_id}", 3600, "1")

    def is_cancel_requested(self, job_id: int) -> bool:
        return bool(self.redis_client.get(f"mailcow:cancel:{job_id}"))

    def clear_cancel(self, job_id: int) -> None:
        self.redis_client.delete(f"mailcow:cancel:{job_id}")

    def request_pause(self, job_id: int) -> None:
        """Flag a running job for a soft pause. The worker honors this at safe
        boundaries (folder changes / DAV item boundaries) rather than freezing
        the transfer mid-request."""
        self.redis_client.setex(f"mailcow:pause:{job_id}", 3600, "1")

    def is_pause_requested(self, job_id: int) -> bool:
        return bool(self.redis_client.get(f"mailcow:pause:{job_id}"))

    def clear_pause(self, job_id: int) -> None:
        self.redis_client.delete(f"mailcow:pause:{job_id}")
    
    def set_job_log(self, job_id: str, log: str) -> None:
        """Store job log in Redis."""
        log_key = f"mailcow:logs:{job_id}"
        self.redis_client.append(log_key, log + "\n")
        # Expire logs after 7 days
        self.redis_client.expire(log_key, 604800)
    
    def get_job_log(self, job_id: str) -> str:
        """Get job log from Redis."""
        log_key = f"mailcow:logs:{job_id}"
        log = self.redis_client.get(log_key)
        return log.decode() if log else ""
    
    def clear_job_log(self, job_id: str) -> None:
        """Clear job log."""
        log_key = f"mailcow:logs:{job_id}"
        self.redis_client.delete(log_key)
