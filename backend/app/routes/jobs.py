from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from app.repositories.job_repo import JobRepository
from app.models import JobStatus, JobCreate, JobResponse
from app.core.queue import RedisQueue
from typing import List

router = APIRouter()
queue = RedisQueue()

class JobCreateRequest(BaseModel):
    source_email: str
    source_password: str
    target_email: str
    target_password: str
    domain: str
    source_host: str = None

@router.post("/create")
async def create_job(request: Request, job_data: JobCreateRequest):
    """Create a new migration job."""
    tenant_id = request.state.tenant_id
    
    # Create job in database
    job = JobRepository.create_job(
        tenant_id=tenant_id,
        source_email=job_data.source_email,
        target_email=job_data.target_email
    )
    
    # Push to queue for processing
    queue_job = {
        "id": job.id,
        "tenant_id": tenant_id,
        "source_email": job_data.source_email,
        "source_password": job_data.source_password,
        "target_email": job_data.target_email,
        "target_password": job_data.target_password,
        "source_host": job_data.source_host,
        "retry_count": 0
    }
    queue.push_job(queue_job)
    
    return {
        "id": job.id,
        "status": JobStatus.PENDING.value,
        "source_email": job.source_email,
        "target_email": job.target_email
    }

@router.get("/list")
async def list_jobs(request: Request, status: str = None, limit: int = 100, offset: int = 0):
    """List jobs for tenant."""
    tenant_id = request.state.tenant_id
    
    job_status = JobStatus(status) if status else None
    jobs = JobRepository.get_jobs_by_tenant(tenant_id, job_status, limit, offset)
    
    return [
        {
            "id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "source_email": job.source_email,
            "target_email": job.target_email,
            "error_message": job.error_message,
            "created_at": job.created_at,
            "completed_at": job.completed_at
        }
        for job in jobs
    ]

@router.post("/retry/{job_id}")
async def retry_job(request: Request, job_id: int):
    """Retry a failed job."""
    tenant_id = request.state.tenant_id
    
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Reset job status
    JobRepository.update_job_status(job_id, tenant_id, JobStatus.PENDING, error_message=None)
    
    # Re-queue job
    queue_job = {
        "id": job.id,
        "tenant_id": tenant_id,
        "source_email": job.source_email,
        "target_email": job.target_email,
        "retry_count": 0
    }
    queue.push_job(queue_job)
    
    return {"status": "queued"}

@router.get("/{job_id}")
async def get_job(request: Request, job_id: int):
    """Get job details."""
    tenant_id = request.state.tenant_id
    
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return {
        "id": job.id,
        "status": job.status.value,
        "progress": job.progress,
        "source_email": job.source_email,
        "target_email": job.target_email,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at
    }
