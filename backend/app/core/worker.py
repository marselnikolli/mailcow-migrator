import time
import logging
import re
from typing import Optional
from app.core.queue import RedisQueue
from app.core.imapsync import CANCELLED, ImapsyncWrapper
from app.core.imapsync_progress import parse_progress_line, parse_folder_selection
from app.core.domains import DomainService
from app.core.mailcow import MailcowClient
from app.core.dav_sync import DavSyncer, DavSyncError
from app.core.secrets import SecretEncryptor
from app.core.notifications import notify_job_event
from app.core.metrics import (
    jobs_total, messages_copied, messages_skipped,
    calendar_items, contacts_items, task_items,
    queue_depth, running_jobs, job_duration,
)
from app.core.logger import StructuredLogger
from app.repositories.job_repo import JobRepository
from app.models import JobStatus

logger = logging.getLogger(__name__)

_COPIED_MSG_RE = re.compile(r"copied to \S+/\d+")


def _redact(text: str, secrets: list) -> str:
    """Strip known secret values out of a string before it's stored or
    streamed. imapsync tries to mask passwords in its own self-printed
    command line, but that masking can fail (e.g. on passwords containing
    regex-special characters) and leak the real value into its output -
    don't rely on it."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


class MigrationWorker:
    def __init__(self):
        from app.config import settings
        self.queue = RedisQueue(lock_timeout=settings.JOB_LOCK_TIMEOUT)
        self.imapsync = ImapsyncWrapper()
        self.job_logger = StructuredLogger()
        self.secrets = SecretEncryptor()
        self.max_retries = 3

    def process_job(self, job: dict) -> bool:
        """Process a single migration job."""
        job_id = job.get("id")
        tenant_id = job.get("tenant_id")
        source_email = job.get("source_email")
        source_password = self.secrets.decrypt(job.get("source_password", ""))
        target_email = job.get("target_email")
        target_password = self.secrets.decrypt(job.get("target_password", ""))
        source_host = job.get("source_host")
        source_port = job.get("source_port", 993)
        source_ssl = job.get("source_ssl", True)
        target_type = job.get("target_type", "imap")
        target_host = job.get("target_host", "localhost")
        target_port = job.get("target_port", 993)
        target_ssl = job.get("target_ssl", True)
        mailcow_url = job.get("mailcow_url")
        mailcow_api_key = self.secrets.decrypt(job.get("mailcow_api_key", ""))
        dry_run = job.get("dry_run", False)
        sync_calendar = job.get("sync_calendar", False)
        sync_contacts = job.get("sync_contacts", False)
        sync_tasks = job.get("sync_tasks", False)
        folders = job.get("folders")
        maxage_days = job.get("maxage_days")
        since_date = job.get("since_date")
        secrets = [s for s in (source_password, target_password, mailcow_api_key) if s]

        job_start = time.time()
        copied_count = 0

        try:
            if self.queue.is_cancel_requested(job_id):
                self.job_logger.log_info(job_id, "Cancelled before processing started")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                return False

            self.job_logger.log_info(job_id, f"Starting migration for {source_email} -> {target_email}")

            if dry_run:
                self.job_logger.log_info(job_id, "DRY RUN mode: no data will be transferred, no mailboxes will be created")

            # Update job status to running + record run tracking state.
            # imapsync is idempotent (skips already-transferred UIDs), so a
            # re-run naturally resumes where the previous run left off.
            prev_runs = JobRepository.get_job_by_id(job_id, tenant_id)
            run_count = (prev_runs.run_count or 0) if prev_runs else 0
            if run_count > 0:
                self.job_logger.log_info(
                    job_id,
                    f"Resuming job (previous runs: {run_count}, "
                    f"last status: {(prev_runs.last_run_status or 'n/a') if prev_runs else 'n/a'})",
                )
            JobRepository.record_run_start(job_id, tenant_id)
            JobRepository.update_job_status(job_id, tenant_id, JobStatus.RUNNING)
            running_jobs.set(self.queue.get_queue_size() + 1)
            
            # Extract domain from target email
            target_domain = target_email.split("@")[1]
            
            # If target is a Mailcow instance, create domain + mailbox via its API (skip on dry run)
            if target_type == "mailcow":
                mailcow = MailcowClient(base_url=mailcow_url, api_key=mailcow_api_key)
                
                self.job_logger.log_info(job_id, f"Ensuring domain {target_domain} exists in Mailcow ({mailcow.base_url})")
                if not dry_run:
                    # Normally already done synchronously when the job was
                    # created/edited (see routes/jobs.py); this is the
                    # fallback for jobs queued before that existed, and also
                    # keeps the local domains table (shown on the Domains
                    # page) in sync with what actually exists in Mailcow.
                    try:
                        DomainService(mailcow=mailcow).ensure_domain_exists(target_domain, tenant_id)
                        self.job_logger.log_info(job_id, f"Domain {target_domain} ready in Mailcow")
                    except Exception as e:
                        raise Exception(f"Failed to prepare domain in Mailcow: {str(e)}")


                    self.job_logger.log_info(job_id, f"Creating mailbox {target_email} in Mailcow")
                    if not mailcow.check_mailbox_exists(target_email):
                        try:
                            mailcow.create_mailbox(target_email, target_password)
                            self.job_logger.log_info(job_id, f"Created mailbox {target_email} in Mailcow")
                        except Exception as e:
                            raise Exception(f"Failed to create mailbox: {str(e)}")
                    else:
                        self.job_logger.log_info(job_id, f"Mailbox {target_email} already exists in Mailcow")
                else:
                    self.job_logger.log_info(job_id, f"Dry run: skipping domain/mailbox creation in Mailcow")
            else:
                # Generic IMAP target - no domain/mailbox creation
                self.job_logger.log_info(job_id, f"Target is generic IMAP server ({target_host}:{target_port}) - skipping domain/mailbox creation")
            
            # Run imapsync with logging
            self.job_logger.log_info(job_id, "Starting IMAP sync")

            # Track the most recent progress line for this folder; folder totals
            # change as imapsync moves between folders, so we only push a DB
            # update when the overall job progress actually moved.
            last_progress_pct = -1

            def on_log(line):
                nonlocal last_progress_pct, copied_count
                line = _redact(line, secrets)
                self.job_logger.log_info(job_id, line)
                self.queue.set_job_log(job_id, line)
                if _COPIED_MSG_RE.search(line):
                    copied_count += 1
                info = parse_progress_line(line)
                if info and info.percent is not None and info.percent != last_progress_pct:
                    last_progress_pct = info.percent
                    JobRepository.update_job_status(
                        job_id, tenant_id, JobStatus.RUNNING,
                        progress=info.percent, error_message=None,
                    )
                folder = parse_folder_selection(line)
                if folder and not dry_run:
                    self.job_logger.log_info(
                        job_id,
                        f"Migrating folder [{folder['folder']}] ({folder['total']} messages)",
                    )
            
            success, output = self.imapsync.run_sync_with_logging(
                source_email=source_email,
                source_password=source_password,
                target_email=target_email,
                target_password=target_password,
                on_log_callback=on_log,
                source_host=source_host,
                source_port=source_port,
                source_ssl=source_ssl,
                target_host=target_host,
                target_port=target_port,
                target_ssl=target_ssl,
                dry_run=dry_run,
                folders=folders,
                maxage_days=maxage_days,
                since_date=since_date,
                should_cancel=lambda: self.queue.is_cancel_requested(job_id)
            )

            if output == CANCELLED:
                self.job_logger.log_info(job_id, "Migration cancelled")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                return False

            if success:
                # Optional CalDAV/CardDAV migration (calendar + address book)
                if sync_calendar or sync_contacts or sync_tasks:
                    if target_type != "mailcow":
                        self.job_logger.log_info(job_id, "Skipping calendar/contacts/tasks sync: target is not a Mailcow/SOGo instance")
                    else:
                        self.job_logger.log_info(job_id, f"Starting calendar/contacts/tasks sync (calendar={sync_calendar}, contacts={sync_contacts}, tasks={sync_tasks})")
                        dav = DavSyncer(
                            source_email=source_email,
                            source_password=source_password,
                            source_host=source_host,
                            source_ssl=source_ssl,
                            target_email=target_email,
                            target_password=target_password,
                            target_host=target_host,
                            target_ssl=target_ssl,
                            on_log=on_log,
                        )
                        try:
                            results = dav.run(
                                sync_calendar=sync_calendar,
                                sync_contacts=sync_contacts,
                                sync_tasks=sync_tasks,
                                dry_run=dry_run,
                            )
                            self.job_logger.log_info(job_id, f"Calendar/contacts sync done: {_redact(str(results), secrets)}")
                            if not dry_run:
                                calendar_items.inc(results.get("calendar", {}).get("uploaded", 0))
                                contacts_items.inc(results.get("contacts", {}).get("uploaded", 0))
                                task_items.inc(results.get("tasks", {}).get("uploaded", 0))
                        except DavSyncError as e:
                            self.job_logger.log_error(job_id, f"Calendar/contacts sync failed: {_redact(str(e), secrets)}")

                if dry_run:
                    self.job_logger.log_info(job_id, "Dry run completed successfully - no data was transferred")
                else:
                    self.job_logger.log_info(job_id, "Migration completed successfully")
                JobRepository.mark_job_completed(job_id, tenant_id)
                JobRepository.record_run_end(job_id, tenant_id, JobStatus.COMPLETED.value)
                job_duration.observe(time.time() - job_start)
                jobs_total.inc(1, labels={"outcome": "completed"})
                messages_copied.inc(copied_count)
                notify_job_event(
                    job_id, "completed",
                    f"Migration {source_email} -> {target_email} completed",
                    {"source": source_email, "target": target_email, "dry_run": dry_run,
                     "copied_messages": copied_count},
                )
                return True
            else:
                raise Exception(f"IMAP sync failed: {output}")

        except Exception as e:
            error_msg = _redact(str(e), secrets)
            self.job_logger.log_error(job_id, error_msg)

            if self.queue.is_cancel_requested(job_id):
                self.job_logger.log_info(job_id, "Migration cancelled")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                JobRepository.record_run_end(job_id, tenant_id, JobStatus.CANCELLED.value)
                job_duration.observe(time.time() - job_start)
                jobs_total.inc(1, labels={"outcome": "cancelled"})
                notify_job_event(job_id, "cancelled", f"Migration {source_email} -> {target_email} cancelled")
                return False

            # Check retry count
            retry_count = job.get("retry_count", 0)
            if retry_count < self.max_retries:
                self.job_logger.log_info(job_id, f"Retrying... (attempt {retry_count + 1}/{self.max_retries})")
                job["retry_count"] = retry_count + 1
                self.queue.push_job(job)
            else:
                JobRepository.record_run_end(job_id, tenant_id, JobStatus.FAILED.value)
                self.job_logger.log_error(job_id, "Max retries exceeded, marking job as failed")
                JobRepository.mark_job_failed(job_id, tenant_id, error_msg)
                job_duration.observe(time.time() - job_start)
                jobs_total.inc(1, labels={"outcome": "failed"})
                messages_copied.inc(copied_count)
                notify_job_event(job_id, "failed", f"Migration {source_email} -> {target_email} failed: {error_msg}")

            return False
    
    def _enqueue_scheduled_jobs(self) -> None:
        """Find enabled jobs whose scheduled run is due and push them to the
        queue, then advance next_run_at. Delta runs reuse the job's folder /
        date filters (imapsync is idempotent, so repeated runs only pull new
        messages)."""
        due = JobRepository.get_due_jobs()
        for job in due:
            interval = job.schedule_interval_minutes or 0
            self.job_logger.log_info(job.id, "Scheduled run due - enqueueing delta sync")
            payload = {
                "id": job.id,
                "tenant_id": job.tenant_id,
                "source_email": job.source_email,
                "source_password": self.secrets.encrypt(job.source_password or ""),
                "target_email": job.target_email,
                "target_password": self.secrets.encrypt(job.target_password or ""),
                "source_host": job.source_host,
                "source_port": job.source_port,
                "source_ssl": job.source_ssl,
                "target_type": job.target_type,
                "target_host": job.target_host,
                "target_port": job.target_port,
                "target_ssl": job.target_ssl,
                "mailcow_url": job.mailcow_url,
                "mailcow_api_key": self.secrets.encrypt(job.mailcow_api_key or ""),
                "dry_run": job.dry_run,
                "sync_calendar": job.sync_calendar,
                "sync_contacts": job.sync_contacts,
                "sync_tasks": job.sync_tasks,
                "folders": job.folders,
                "maxage_days": job.maxage_days,
                "since_date": job.since_date,
                "retry_count": 0,
            }
            self.queue.push_job(payload)
            JobRepository.schedule_next_run(job.id, job.tenant_id, interval or 1440)

    def start(self, poll_interval: int = 5, schedule_interval: int = 30):
        """Start the worker loop."""
        logger.info("Migration worker started")
        
        # Scheduler tick counter: scan for due scheduled jobs every
        # `schedule_interval` seconds.
        ticks_since_schedule = 0

        while True:
            try:
                # Pop job from queue
                job = self.queue.pop_job()
                
                if job:
                    logger.info(f"Processing job {job.get('id')}")
                    queue_depth.set(self.queue.get_queue_size())
                    try:
                        self.process_job(job)
                    finally:
                        # Release the queue lock regardless of outcome so a
                        # crashed/heartbeat-less run doesn't hold it forever.
                        self.queue.release_job_lock(job.get("job_id"))
                        queue_depth.set(self.queue.get_queue_size())
                else:
                    # No job available, sleep briefly
                    time.sleep(poll_interval)

                # Scan for due scheduled jobs on a slower cadence.
                ticks_since_schedule += poll_interval
                if ticks_since_schedule >= schedule_interval:
                    ticks_since_schedule = 0
                    self._enqueue_scheduled_jobs()
            
            except Exception as e:
                logger.error(f"Worker error: {str(e)}")
                time.sleep(poll_interval)

if __name__ == "__main__":
    MigrationWorker().start()
