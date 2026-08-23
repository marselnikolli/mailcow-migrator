from fastapi import APIRouter, Request, HTTPException, Depends, File, UploadFile
from pydantic import BaseModel
from typing import List
from app.repositories.job_repo import JobRepository
from app.models import JobStatus, JobCreate, JobResponse, BulkJobCreate, ImportedAccount
from app.core.queue import RedisQueue
from app.core.import_parser import parse_import

router = APIRouter()
queue = RedisQueue()


def _to_queue_job(job: JobCreate, tenant_id: int, db_job_id: int) -> dict:
    return {
        "id": db_job_id,
        "tenant_id": tenant_id,
        "source_email": job.source_email,
        "source_password": job.source_password,
        "target_email": job.target_email,
        "target_password": job.target_password,
        "source_host": job.source_server.host,
        "source_port": job.source_server.port,
        "source_ssl": job.source_server.ssl,
        "target_type": job.target_type,
        "target_host": job.target_server.host,
        "target_port": job.target_server.port,
        "target_ssl": job.target_server.ssl,
        "mailcow_url": job.mailcow_url,
        "mailcow_api_key": job.mailcow_api_key,
        "dry_run": job.dry_run,
        "retry_count": 0
    }


@router.post("/create")
async def create_job(request: Request, job_data: JobCreate):
    """Create a new migration job."""
    tenant_id = request.state.tenant_id
    
    # Create job in database
    job = JobRepository.create_job(
        tenant_id=tenant_id,
        source_email=job_data.source_email,
        target_email=job_data.target_email,
        source_password=job_data.source_password,
        target_password=job_data.target_password,
        source_host=job_data.source_server.host,
        source_port=job_data.source_server.port,
        source_ssl=job_data.source_server.ssl,
        target_type=job_data.target_type,
        target_host=job_data.target_server.host,
        target_port=job_data.target_server.port,
        target_ssl=job_data.target_server.ssl,
        mailcow_url=job_data.mailcow_url,
        mailcow_api_key=job_data.mailcow_api_key,
        dry_run=job_data.dry_run
    )
    
    # Push to queue for processing
    queue.push_job(_to_queue_job(job_data, tenant_id, job.id))
    
    return {
        "id": job.id,
        "status": JobStatus.PENDING.value,
        "source_email": job.source_email,
        "target_email": job.target_email,
        "target_type": job.target_type,
        "dry_run": job.dry_run
    }


@router.post("/bulk-create")
async def bulk_create_jobs(request: Request, bulk_data: BulkJobCreate):
    """Create multiple migration jobs at once (e.g. from an imported list)."""
    tenant_id = request.state.tenant_id
    
    if not bulk_data.jobs:
        raise HTTPException(status_code=400, detail="No jobs provided")
    
    created = []
    for job_data in bulk_data.jobs:
        job = JobRepository.create_job(
            tenant_id=tenant_id,
            source_email=job_data.source_email,
            target_email=job_data.target_email,
            source_password=job_data.source_password,
            target_password=job_data.target_password,
            source_host=job_data.source_server.host,
            source_port=job_data.source_server.port,
            source_ssl=job_data.source_server.ssl,
            target_type=job_data.target_type,
            target_host=job_data.target_server.host,
            target_port=job_data.target_server.port,
            target_ssl=job_data.target_server.ssl,
            mailcow_url=job_data.mailcow_url,
            mailcow_api_key=job_data.mailcow_api_key,
            dry_run=job_data.dry_run
        )
        queue.push_job(_to_queue_job(job_data, tenant_id, job.id))
        created.append({
            "id": job.id,
            "status": JobStatus.PENDING.value,
            "source_email": job.source_email,
            "target_email": job.target_email,
            "dry_run": job.dry_run
        })
    
    return {"total": len(created), "jobs": created}


@router.post("/import-preview")
async def import_preview(file: UploadFile = File(...)):
    """Parse an uploaded CSV/XLSX/JSON account file and return the parsed list."""
    content = await file.read()
    try:
        accounts = parse_import(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {"total": len(accounts), "accounts": accounts}


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
            "source_host": job.source_host,
            "target_type": job.target_type,
            "target_host": job.target_host,
            "dry_run": job.dry_run,
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
    
    # Re-queue job with full config
    queue_job = {
        "id": job.id,
        "tenant_id": tenant_id,
        "source_email": job.source_email,
        "source_password": job.source_password or "",
        "target_email": job.target_email,
        "target_password": job.target_password or "",
        "source_host": job.source_host,
        "source_port": job.source_port,
        "source_ssl": job.source_ssl,
        "target_type": job.target_type,
        "target_host": job.target_host,
        "target_port": job.target_port,
        "target_ssl": job.target_ssl,
        "mailcow_url": job.mailcow_url,
        "mailcow_api_key": job.mailcow_api_key,
        "dry_run": job.dry_run,
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
        "source_host": job.source_host,
        "target_type": job.target_type,
        "target_host": job.target_host,
        "mailcow_url": job.mailcow_url,
        "dry_run": job.dry_run,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at
    }
