"""Shared Redis queue payload builder.

The queue holds a snapshot of the job's settings, serialized as JSON. Three
call sites used to build this dict independently (create/bulk-create, retry/
edit, and the scheduled-run enqueuer in the worker) and had already drifted;
this is the single source of truth. Secrets must be encrypted by the caller
before being passed in -- this module never touches the encryptor.
"""

from typing import Optional


def build_queue_payload(
    *,
    id: int,
    tenant_id: int,
    source_email: str,
    source_password: str,
    target_email: str,
    target_password: str,
    source_host: Optional[str],
    source_port: int,
    source_ssl: bool,
    target_type: str,
    target_host: Optional[str],
    target_port: int,
    target_ssl: bool,
    mailcow_url: Optional[str],
    mailcow_api_key: Optional[str],
    dry_run: bool,
    sync_calendar: bool,
    sync_contacts: bool,
    sync_tasks: bool,
    folders: Optional[str],
    maxage_days: Optional[int],
    since_date: Optional[str],
    enabled: bool,
    schedule_interval_minutes: Optional[int],
    retry_count: int = 0,
) -> dict:
    """Package a job's settings into the JSON blob stored in Redis."""
    return {
        "id": id,
        "tenant_id": tenant_id,
        "source_email": source_email,
        "source_password": source_password,
        "target_email": target_email,
        "target_password": target_password,
        "source_host": source_host,
        "source_port": source_port,
        "source_ssl": source_ssl,
        "target_type": target_type,
        "target_host": target_host,
        "target_port": target_port,
        "target_ssl": target_ssl,
        "mailcow_url": mailcow_url,
        "mailcow_api_key": mailcow_api_key,
        "dry_run": dry_run,
        "sync_calendar": sync_calendar,
        "sync_contacts": sync_contacts,
        "sync_tasks": sync_tasks,
        "folders": folders,
        "maxage_days": maxage_days,
        "since_date": since_date,
        "enabled": enabled,
        "schedule_interval_minutes": schedule_interval_minutes,
        "retry_count": retry_count,
    }
