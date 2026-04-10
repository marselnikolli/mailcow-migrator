import redis
import json
from typing import Optional, Dict, Any
from app.config import settings
import uuid

class RedisQueue:
    def __init__(self):
        self.redis_client = redis.from_url(settings.REDIS_URL)
        self.queue_key = "mailcow:jobs:queue"
        self.processing_key = "mailcow:jobs:processing"
    
    def push_job(self, job: Dict[str, Any]) -> str:
        """Push a job to the queue."""
        job_id = str(uuid.uuid4())
        job["job_id"] = job_id
        job_json = json.dumps(job)
        self.redis_client.lpush(self.queue_key, job_json)
        return job_id
    
    def pop_job(self) -> Optional[Dict[str, Any]]:
        """Pop job from queue with locking."""
        # Pop from queue
        job_json = self.redis_client.rpop(self.queue_key)
        if not job_json:
            return None
        
        job = json.loads(job_json)
        # Add to processing set with lock
        job_id = job.get("job_id")
        lock_key = f"mailcow:lock:{job_id}"
        
        # Set lock with 1 hour expiry
        self.redis_client.setex(lock_key, 3600, "1")
        
        return job
    
    def acquire_job_lock(self, job_id: str, timeout: int = 3600) -> bool:
        """Try to acquire lock on job."""
        lock_key = f"mailcow:lock:{job_id}"
        return bool(self.redis_client.setex(lock_key, timeout, "1"))
    
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
