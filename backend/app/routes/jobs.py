from fastapi import APIRouter, Request, HTTPException, Depends, File, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List
from urllib.parse import urlparse
from app.repositories.job_repo import JobRepository
from app.models import JobStatus, JobCreate, JobResponse, BulkJobCreate, ImportedAccount, JobUpdate, Job
from app.core.queue import RedisQueue
from app.core.report import build_report, report_to_csv
from app.core.estimate import MailboxEstimator
from app.core.autodiscover import discover_imap_host
from app.core.import_parser import parse_import
from app.core.security import UnsafeUrlError, validate_public_url
from app.core.secrets import SecretEncryptor
from app.core.domains import DomainService
from app.core.mailcow import MailcowClient
from app.deps.roles import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])
queue = RedisQueue()
_secrets = SecretEncryptor()


def _validate_job_targets(job: JobCreate) -> None:
    """Reject jobs whose mailcow_url would make the worker issue requests to
    internal/private network addresses (SSRF)."""
    try:
        validate_public_url(job.mailcow_url, field_name="mailcow_url")
    except UnsafeUrlError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _ensure_target_domain(target_email: str, target_type: str, mailcow_url: str,
                           mailcow_api_key: str, dry_run: bool, tenant_id: int) -> None:
    """If the destination is a Mailcow instance, make sure the target
    mailbox's domain exists there (creating it if needed) before the job is
    queued, rather than leaving it to whenever a worker happens to pick the
    job up. Skipped on dry runs, which shouldn't create anything for real."""
    if target_type != "mailcow" or dry_run:
        return

    domain = target_email.split("@")[-1].strip().lower()
    if not domain:
        return

    mailcow = MailcowClient(base_url=mailcow_url, api_key=mailcow_api_key)
    DomainService(mailcow=mailcow).ensure_domain_exists(domain, tenant_id)


def _apply_defaults(job: JobCreate) -> JobCreate:
    """Mirror source -> target by default.

    When no target email is provided, the new mailbox keeps the source address.
    When no target password is provided, it keeps the source password.
    """
    target_email = (job.target_email or "").strip() or job.source_email.strip()
    target_password = job.target_password or job.source_password
    target_type = job.target_type or ("mailcow" if (job.mailcow_url or job.mailcow_api_key) else "imap")

    target_server = job.target_server
    if target_type == "mailcow" and job.mailcow_url and target_server.host in ("localhost", "127.0.0.1", ""):
        # "localhost" is only meaningful if imapsync runs on the mail server
        # itself; it runs in an isolated worker container here, so that
        # default can never reach anything. Point the IMAP transfer at the
        # Mailcow instance's own hostname instead, unless the caller set an
        # explicit host of their own.
        mailcow_host = urlparse(job.mailcow_url).hostname
        if mailcow_host:
            target_server = target_server.model_copy(update={"host": mailcow_host})

    # Pydantic model needs copy() with updated fields
    return job.model_copy(update={
        "target_email": target_email,
        "target_password": target_password,
        "target_type": target_type,
        "target_server": target_server,
    })


def _to_queue_job(job: JobCreate, tenant_id: int, db_job_id: int) -> dict:
    return {
        "id": db_job_id,
        "tenant_id": tenant_id,
        "source_email": job.source_email,
        "source_password": _secrets.encrypt(job.source_password),
        "target_email": job.target_email,
        "target_password": _secrets.encrypt(job.target_password),
        "source_host": job.source_server.host,
        "source_port": job.source_server.port,
        "source_ssl": job.source_server.ssl,
        "target_type": job.target_type,
        "target_host": job.target_server.host,
        "target_port": job.target_server.port,
        "target_ssl": job.target_server.ssl,
        "mailcow_url": job.mailcow_url,
        "mailcow_api_key": _secrets.encrypt(job.mailcow_api_key or ""),
        "dry_run": job.dry_run,
        "sync_calendar": job.sync_calendar,
        "sync_contacts": job.sync_contacts,
        "sync_tasks": job.sync_tasks,
        "folders": job.folders,
        "maxage_days": job.maxage_days,
        "since_date": job.since_date,
        "enabled": job.enabled,
        "schedule_interval_minutes": job.schedule_interval_minutes,
        "retry_count": 0
    }


def _job_to_queue_dict(job: Job, tenant_id: int) -> dict:
    """Build a worker queue payload from a stored Job row (used by retry/edit,
    where we start from the DB record rather than a fresh JobCreate)."""
    return {
        "id": job.id,
        "tenant_id": tenant_id,
        "source_email": job.source_email,
        "source_password": _secrets.encrypt(job.source_password or ""),
        "target_email": job.target_email,
        "target_password": _secrets.encrypt(job.target_password or ""),
        "source_host": job.source_host,
        "source_port": job.source_port,
        "source_ssl": job.source_ssl,
        "target_type": job.target_type,
        "target_host": job.target_host,
        "target_port": job.target_port,
        "target_ssl": job.target_ssl,
        "mailcow_url": job.mailcow_url,
        "mailcow_api_key": _secrets.encrypt(job.mailcow_api_key or ""),
        "dry_run": job.dry_run,
        "sync_calendar": job.sync_calendar,
        "sync_contacts": job.sync_contacts,
        "sync_tasks": job.sync_tasks,
        "folders": job.folders,
        "maxage_days": job.maxage_days,
        "since_date": job.since_date,
        "enabled": job.enabled,
        "schedule_interval_minutes": job.schedule_interval_minutes,
        "retry_count": 0
    }


@router.post("/create")
async def create_job(request: Request, job_data: JobCreate):
    """Create a new migration job."""
    tenant_id = request.state.tenant_id

    job_data = _apply_defaults(job_data)
    _validate_job_targets(job_data)

    try:
        _ensure_target_domain(
            job_data.target_email, job_data.target_type,
            job_data.mailcow_url, job_data.mailcow_api_key,
            job_data.dry_run, tenant_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
        dry_run=job_data.dry_run,
        sync_calendar=job_data.sync_calendar,
        sync_contacts=job_data.sync_contacts,
        sync_tasks=job_data.sync_tasks,
        folders=job_data.folders,
        maxage_days=job_data.maxage_days,
        since_date=job_data.since_date,
        enabled=job_data.enabled,
        schedule_interval_minutes=job_data.schedule_interval_minutes
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
    failed = []
    # Domains are looked up/created at most once per distinct domain in this
    # batch, since bulk imports commonly bring in many mailboxes on the same
    # domain and there's no need to re-check Mailcow for each one.
    checked_domains = set()

    for job_data in bulk_data.jobs:
        job_data = _apply_defaults(job_data)
        try:
            _validate_job_targets(job_data)
            domain = job_data.target_email.split("@")[-1].strip().lower()
            if job_data.target_type == "mailcow" and not job_data.dry_run and domain not in checked_domains:
                _ensure_target_domain(
                    job_data.target_email, job_data.target_type,
                    job_data.mailcow_url, job_data.mailcow_api_key,
                    job_data.dry_run, tenant_id
                )
                checked_domains.add(domain)
        except HTTPException as e:
            failed.append({"source_email": job_data.source_email, "error": str(e.detail)})
            continue
        except Exception as e:
            failed.append({"source_email": job_data.source_email, "error": str(e)})
            continue

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
            dry_run=job_data.dry_run,
            sync_calendar=job_data.sync_calendar,
            sync_contacts=job_data.sync_contacts,
            sync_tasks=job_data.sync_tasks,
            folders=job_data.folders,
            maxage_days=job_data.maxage_days,
            since_date=job_data.since_date,
            enabled=job_data.enabled,
            schedule_interval_minutes=job_data.schedule_interval_minutes
        )
        queue.push_job(_to_queue_job(job_data, tenant_id, job.id))
        created.append({
            "id": job.id,
            "status": JobStatus.PENDING.value,
            "source_email": job.source_email,
            "target_email": job.target_email,
            "dry_run": job.dry_run
        })

    return {"total": len(created), "jobs": created, "failed": failed}


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
            "sync_calendar": job.sync_calendar,
            "sync_contacts": job.sync_contacts,
            "sync_tasks": job.sync_tasks,
            "last_run_at": job.last_run_at,
            "last_run_status": job.last_run_status,
            "run_count": job.run_count,
            "folders": job.folders,
            "maxage_days": job.maxage_days,
            "since_date": job.since_date,
            "enabled": job.enabled,
            "schedule_interval_minutes": job.schedule_interval_minutes,
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
    queue.push_job(_job_to_queue_dict(job, tenant_id))

    return {"status": "queued"}


@router.put("/{job_id}")
async def update_job(request: Request, job_id: int, update: JobUpdate):
    """Edit a job's destination configuration. Only allowed while the job is
    still pending (a worker hasn't picked it up yet)."""
    tenant_id = request.state.tenant_id

    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in (JobStatus.PENDING, JobStatus.FAILED):
        raise HTTPException(status_code=400, detail="Only pending or failed jobs can be edited")

    fields = {}
    if update.target_email is not None:
        fields["target_email"] = update.target_email.strip() or job.source_email
    if update.target_password is not None:
        fields["target_password"] = _secrets.encrypt(update.target_password)
    if update.target_type is not None:
        fields["target_type"] = update.target_type
    if update.mailcow_url is not None:
        try:
            validate_public_url(update.mailcow_url, field_name="mailcow_url")
        except UnsafeUrlError as e:
            raise HTTPException(status_code=400, detail=str(e))
        fields["mailcow_url"] = update.mailcow_url
    if update.target_server is not None:
        host = update.target_server.host
        effective_target_type = fields.get("target_type", job.target_type)
        effective_mailcow_url = fields.get("mailcow_url", job.mailcow_url)
        if effective_target_type == "mailcow" and effective_mailcow_url and host in ("localhost", "127.0.0.1", ""):
            derived_host = urlparse(effective_mailcow_url).hostname
            if derived_host:
                host = derived_host
        fields["target_host"] = host
        fields["target_port"] = update.target_server.port
        fields["target_ssl"] = int(update.target_server.ssl)
    if update.mailcow_api_key is not None:
        fields["mailcow_api_key"] = _secrets.encrypt(update.mailcow_api_key)
    if update.dry_run is not None:
        fields["dry_run"] = int(update.dry_run)
    if update.sync_calendar is not None:
        fields["sync_calendar"] = int(update.sync_calendar)
    if update.sync_contacts is not None:
        fields["sync_contacts"] = int(update.sync_contacts)
    if update.sync_tasks is not None:
        fields["sync_tasks"] = int(update.sync_tasks)
    if update.folders is not None:
        fields["folders"] = update.folders
    if update.maxage_days is not None:
        fields["maxage_days"] = update.maxage_days
    if update.since_date is not None:
        fields["since_date"] = update.since_date
    if update.enabled is not None:
        fields["enabled"] = int(update.enabled)
    if update.schedule_interval_minutes is not None:
        fields["schedule_interval_minutes"] = update.schedule_interval_minutes

    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    effective_target_email = fields.get("target_email", job.target_email)
    effective_target_type = fields.get("target_type", job.target_type)
    effective_mailcow_url = fields.get("mailcow_url", job.mailcow_url)
    effective_mailcow_api_key = fields.get("mailcow_api_key", job.mailcow_api_key)
    effective_dry_run = bool(fields.get("dry_run", job.dry_run))

    try:
        _ensure_target_domain(
            effective_target_email, effective_target_type,
            effective_mailcow_url, effective_mailcow_api_key,
            effective_dry_run, tenant_id
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    JobRepository.update_job(job_id, tenant_id, **fields)

    # The queue holds a snapshot taken at creation time. Drop it and push a
    # fresh one so the worker picks up the edit; if it's already gone (a
    # worker grabbed it in the race window right before this request), the
    # DB update above still stands as the record of what was requested.
    if queue.remove_job(job_id):
        updated_job = JobRepository.get_job_by_id(job_id, tenant_id)
        queue.push_job(_job_to_queue_dict(updated_job, tenant_id))

    return {"status": "updated", "id": job_id}


@router.post("/{job_id}/cancel")
async def cancel_job(request: Request, job_id: int):
    """Cancel a pending or running job."""
    tenant_id = request.state.tenant_id

    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"Job is already {job.status.value}")

    still_queued = queue.remove_job(job_id)
    if not still_queued:
        # Already picked up by a worker - ask it to stop between log lines.
        queue.request_cancel(job_id)

    JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.progress)
    return {"status": "cancelled", "id": job_id}


@router.delete("/{job_id}")
async def delete_job(request: Request, job_id: int):
    """Delete a job and its logs. Running jobs must be cancelled first."""
    tenant_id = request.state.tenant_id

    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status == JobStatus.RUNNING:
        raise HTTPException(status_code=400, detail="Cancel the job before deleting it")

    queue.remove_job(job_id)
    queue.clear_job_log(job_id)
    queue.clear_cancel(job_id)
    JobRepository.delete_job(job_id, tenant_id)

    return {"status": "deleted", "id": job_id}


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
        "target_port": job.target_port,
        "target_ssl": job.target_ssl,
        "mailcow_url": job.mailcow_url,
        "dry_run": job.dry_run,
        "sync_calendar": job.sync_calendar,
        "sync_contacts": job.sync_contacts,
        "sync_tasks": job.sync_tasks,
        "last_run_at": job.last_run_at,
        "last_run_status": job.last_run_status,
        "run_count": job.run_count,
        "folders": job.folders,
        "maxage_days": job.maxage_days,
        "since_date": job.since_date,
        "enabled": job.enabled,
        "schedule_interval_minutes": job.schedule_interval_minutes,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "completed_at": job.completed_at
    }


@router.get("/{job_id}/report")
async def get_job_report(request: Request, job_id: int):
    """Get a structured migration report for a job, parsed from its log."""
    tenant_id = request.state.tenant_id
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    log = queue.get_job_log(job_id)
    report = build_report(job_id, log, job_meta={
        "source_email": job.source_email,
        "target_email": job.target_email,
        "status": job.status.value,
        "run_count": job.run_count,
        "last_run_status": job.last_run_status,
    })
    return report


@router.get("/{job_id}/report.csv")
async def get_job_report_csv(request: Request, job_id: int):
    """Export a job's migration report as CSV."""
    tenant_id = request.state.tenant_id
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    log = queue.get_job_log(job_id)
    report = build_report(job_id, log, job_meta={
        "source_email": job.source_email,
        "target_email": job.target_email,
    })
    csv_data = report_to_csv(report)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="job-{job_id}-report.csv"'
        },
    )


@router.get("/{job_id}/estimate")
async def get_job_estimate(request: Request, job_id: int):
    """Connect to the source and estimate mailbox size / folder counts without
    transferring anything. Useful before a real migration to size the target."""
    tenant_id = request.state.tenant_id
    job = JobRepository.get_job_by_id(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    try:
        estimator = MailboxEstimator(
            host=job.source_host or "",
            email=job.source_email,
            password=job.source_password,
            port=job.source_port or 993,
            use_ssl=job.source_ssl,
        )
        estimate = estimator.estimate(folders=job.folders)
        return estimate
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Estimate failed: {str(e)}")


@router.get("/autodiscover/{email}")
async def autodiscover_source(request: Request, email: str):
    """Probe the source domain for a reachable IMAP server (SRV, common
    hostnames, MX). Returns the discovered host/port or the default."""
    from app.config import settings
    host, port = discover_imap_host(
        email,
        default_host=settings.SOURCE_IMAP_HOST,
        default_port=settings.SOURCE_IMAP_PORT,
    )
    return {"email": email, "host": host, "port": port}
