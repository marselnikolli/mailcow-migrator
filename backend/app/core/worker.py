import time
import logging
import re
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from app.core.queue import RedisQueue
from app.core.payloads import build_queue_payload
from app.core.imapsync import CANCELLED, ImapsyncWrapper
from app.core.imapsync_progress import parse_progress_line, parse_folder_selection
from app.core.domains import DomainService
from app.core.mailcow import MailcowClient
from app.core.dav_sync import DavSyncer, DavSyncError, PauseRequested
from app.core.estimate import MailboxEstimator
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
        self.max_concurrent_jobs = max(1, settings.MAX_CONCURRENT_JOBS)
        # Tracks how many of the pool's slots are currently in use. The
        # dispatcher only hands a job to the pool when a slot is free, so a
        # busy pool leaves the entry in Redis (durable across crashes) instead
        # of buffering it in the executor's in-memory queue.
        self._slots = threading.BoundedSemaphore(self.max_concurrent_jobs)
        # Number of jobs currently being processed by the worker pool (used for
        # the running_jobs gauge).
        self._active = 0
        self._active_lock = threading.Lock()

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

            if self.queue.is_pause_requested(job_id):
                self.job_logger.log_info(job_id, "Paused before processing started")
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.PAUSED, progress=job.get("progress", 0))
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
            JobRepository.update_job_status(job_id, tenant_id, JobStatus.RUNNING, progress=job.get("progress", 0), error_message=None)
            
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
            last_counts_write = 0.0

            def on_log(line):
                nonlocal last_progress_pct, copied_count, last_counts_write
                line = _redact(line, secrets)
                self.job_logger.log_info(job_id, line)
                self.queue.set_job_log(job_id, line)
                if _COPIED_MSG_RE.search(line):
                    copied_count += 1
                info = parse_progress_line(line)
                folder = parse_folder_selection(line)
                if folder and not dry_run:
                    self.job_logger.log_info(
                        job_id,
                        f"Migrating folder [{folder['folder']}] ({folder['total']} messages)",
                    )

                # Persist itemized counts + weighted progress + ETA on progress
                # change or every ~2s, so the table's progress bar tracks the
                # real rate without hammering the DB per imapsync line.
                now = time.time()
                percent_changed = info and info.percent is not None and info.percent != last_progress_pct
                if percent_changed or now - last_counts_write >= 2.0:
                    if percent_changed:
                        last_progress_pct = info.percent
                    pct, eta = self._weighted_progress(job_id, tenant_id, copied_count, job_start)
                    JobRepository.update_job_counts(
                        job_id, tenant_id,
                        copied_messages=copied_count,
                        progress=pct,
                        eta_seconds=eta,
                    )
                    if percent_changed:
                        JobRepository.update_job_status(
                            job_id, tenant_id, JobStatus.RUNNING,
                            progress=pct, error_message=None,
                        )
                    last_counts_write = now

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
                should_cancel=lambda: (
                    self.queue.is_cancel_requested(job_id)
                    or self.queue.is_pause_requested(job_id)
                )
            )

            if output == CANCELLED:
                if self.queue.is_pause_requested(job_id):
                    JobRepository.update_job_counts(job_id, tenant_id, copied_messages=copied_count)
                    self.job_logger.log_info(job_id, "Migration paused")
                    JobRepository.update_job_status(job_id, tenant_id, JobStatus.PAUSED, progress=job.get("progress", 0))
                    JobRepository.record_run_end(job_id, tenant_id, JobStatus.PAUSED.value)
                    return False
                self.job_logger.log_info(job_id, "Migration cancelled")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                return False

            if success:
                # Soft pause point between the IMAP and DAV phases.
                if self.queue.is_pause_requested(job_id):
                    JobRepository.update_job_counts(job_id, tenant_id, copied_messages=copied_count)
                    self.job_logger.log_info(job_id, "Migration paused after IMAP sync")
                    JobRepository.update_job_status(job_id, tenant_id, JobStatus.PAUSED, progress=job.get("progress", 0))
                    JobRepository.record_run_end(job_id, tenant_id, JobStatus.PAUSED.value)
                    return False

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
                            should_pause=lambda: self.queue.is_pause_requested(job_id),
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
                            JobRepository.update_job_counts(
                                job_id, tenant_id,
                                calendar_copied=results.get("calendar", {}).get("uploaded", 0),
                                contacts_copied=results.get("contacts", {}).get("uploaded", 0),
                                tasks_copied=results.get("tasks", {}).get("uploaded", 0),
                            )
                        except PauseRequested:
                            self.job_logger.log_info(job_id, "Migration paused during calendar/contacts/tasks sync")
                            JobRepository.update_job_status(job_id, tenant_id, JobStatus.PAUSED, progress=job.get("progress", 0))
                            JobRepository.record_run_end(job_id, tenant_id, JobStatus.PAUSED.value)
                            return False
                        except DavSyncError as e:
                            self.job_logger.log_error(job_id, f"Calendar/contacts sync failed: {_redact(str(e), secrets)}")

                if dry_run:
                    self.job_logger.log_info(job_id, "Dry run completed successfully - no data was transferred")
                else:
                    self.job_logger.log_info(job_id, "Migration completed successfully")
                JobRepository.update_job_counts(
                    job_id, tenant_id,
                    copied_messages=copied_count,
                    progress=100,
                    eta_seconds=None,
                )
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

            if self.queue.is_pause_requested(job_id):
                JobRepository.update_job_counts(job_id, tenant_id, copied_messages=copied_count)
                self.job_logger.log_info(job_id, "Migration paused")
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.PAUSED, progress=job.get("progress", 0))
                JobRepository.record_run_end(job_id, tenant_id, JobStatus.PAUSED.value)
                return False

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
    
    def _weighted_progress(self, job_id: int, tenant_id: int, copied_count: int,
                           job_start: float) -> tuple:
        """Compute overall percent + ETA from itemized counts vs expected_total
        (the pre-migration scan's sum). Returns (0, None) when the scan hasn't
        produced a total yet, so callers fall back gracefully."""
        job = JobRepository.get_job_by_id(job_id, tenant_id)
        expected = (job.expected_total or 0) if job else 0
        pct = 0
        eta = None
        if expected > 0:
            pct = min(100, int(copied_count / expected * 100))
            elapsed = time.time() - job_start
            if elapsed > 5 and copied_count > 0:
                rate = copied_count / elapsed
                remaining = max(0, expected - copied_count)
                if rate > 0:
                    eta = int(remaining / rate)
        return pct, eta

    def process_scan(self, payload: dict) -> None:
        """Run a pre-migration scan: count what would actually be migrated
        (IMAP messages honoring folder/date filters, plus calendar/contacts/
        tasks) and store the totals on the job row so the UI can show a real
        progress bar. Read-only - nothing is transferred."""
        job_id = payload.get("id")
        tenant_id = payload.get("tenant_id")
        source_email = payload.get("source_email")
        source_password = self.secrets.decrypt(payload.get("source_password", ""))
        source_host = payload.get("source_host") or ""
        source_port = payload.get("source_port") or 993
        source_ssl = payload.get("source_ssl", True)
        folders = payload.get("folders")
        maxage_days = payload.get("maxage_days")
        since_date = payload.get("since_date")
        sync_calendar = payload.get("sync_calendar", False)
        sync_contacts = payload.get("sync_contacts", False)
        sync_tasks = payload.get("sync_tasks", False)
        secrets = [source_password]

        self.job_logger.log_info(job_id, "Starting pre-migration scan")
        JobRepository.update_job(job_id, tenant_id, scan_status="scanning")

        try:
            estimator = MailboxEstimator(
                host=source_host,
                email=source_email,
                password=source_password,
                port=source_port,
                use_ssl=source_ssl,
            )
            estimate = estimator.estimate(
                folders=folders,
                maxage_days=maxage_days,
                since_date=since_date,
            )
            total_messages = estimate.get("total_messages", 0)

            # CalDAV/CardDAV counts: reuse the REPORT-only counting path (the
            # same probes dry-run uses) - no writes to the destination.
            dav = DavSyncer(
                source_email=source_email,
                source_password=source_password,
                source_host=source_host,
                source_ssl=source_ssl,
                target_email=source_email,
                target_password="",
                target_host="",
            )
            dav_est = dav.estimate(
                sync_calendar=sync_calendar,
                sync_contacts=sync_contacts,
                sync_tasks=sync_tasks,
            )
            total_calendar = dav_est.get("calendar", 0)
            total_contacts = dav_est.get("contacts", 0)
            total_tasks = dav_est.get("tasks", 0)
            expected_total = total_messages + total_calendar + total_contacts + total_tasks

            JobRepository.update_job(
                job_id, tenant_id,
                scan_status="done",
                total_messages=total_messages,
                total_calendar=total_calendar,
                total_contacts=total_contacts,
                total_tasks=total_tasks,
                expected_total=expected_total,
            )
            self.job_logger.log_info(
                job_id,
                f"Scan complete: {total_messages} messages, {total_calendar} calendar, "
                f"{total_contacts} contacts, {total_tasks} tasks",
            )
        except Exception as e:
            error_msg = _redact(str(e), secrets)
            JobRepository.update_job(job_id, tenant_id, scan_status="failed")
            self.job_logger.log_error(job_id, f"Pre-migration scan failed: {error_msg}")

    def _enqueue_scheduled_jobs(self) -> None:
        """Find enabled jobs whose scheduled run is due and push them to the
        queue, then advance next_run_at. Delta runs reuse the job's folder /
        date filters (imapsync is idempotent, so repeated runs only pull new
        messages)."""
        due = JobRepository.get_due_jobs()
        for job in due:
            interval = job.schedule_interval_minutes or 0
            self.job_logger.log_info(job.id, "Scheduled run due - enqueueing delta sync")
            payload = build_queue_payload(
                id=job.id,
                tenant_id=job.tenant_id,
                source_email=job.source_email,
                source_password=self.secrets.encrypt(job.source_password or ""),
                target_email=job.target_email,
                target_password=self.secrets.encrypt(job.target_password or ""),
                source_host=job.source_host,
                source_port=job.source_port,
                source_ssl=job.source_ssl,
                target_type=job.target_type,
                target_host=job.target_host,
                target_port=job.target_port,
                target_ssl=job.target_ssl,
                mailcow_url=job.mailcow_url,
                mailcow_api_key=self.secrets.encrypt(job.mailcow_api_key or ""),
                dry_run=job.dry_run,
                sync_calendar=job.sync_calendar,
                sync_contacts=job.sync_contacts,
                sync_tasks=job.sync_tasks,
                folders=job.folders,
                maxage_days=job.maxage_days,
                since_date=job.since_date,
                enabled=job.enabled,
                schedule_interval_minutes=job.schedule_interval_minutes,
            )
            self.queue.push_job(payload)
            JobRepository.schedule_next_run(job.id, job.tenant_id, interval or 1440)

    def _pop(self):
        """Pop the next task, scans first (they're fast and feed the progress
        bars the UI polls). Returns (job, source) or (None, None)."""
        scan = self.queue.pop_scan()
        if scan is not None:
            return scan, "scan"
        job = self.queue.pop_job()
        if job is not None:
            return job, "migrate"
        return None, None

    def _run_job(self, job: dict, source: str):
        """Worker thread body: process one queue entry and always release its
        lock and pool slot so a crashed run doesn't hold them forever (the
        lock also has a TTL)."""
        job_id = job.get("id")
        with self._active_lock:
            self._active += 1
            running_jobs.set(self._active)
        try:
            if source == "scan":
                self.process_scan(job)
            else:
                self.process_job(job)
        except Exception as e:
            logger.error(f"Worker thread error for job {job_id}: {str(e)}")
        finally:
            if job_id is not None:
                self.queue.release_job_lock(job_id)
            with self._active_lock:
                self._active = max(0, self._active - 1)
                running_jobs.set(self._active)
            queue_depth.set(self.queue.get_queue_size())
            self._slots.release()

    def start(self, poll_interval: int = 5, schedule_interval: int = 30):
        """Start the worker: a single dispatcher loop hands queue entries to a
        pool of up to `max_concurrent_jobs` worker threads. Redis RPOP is
        atomic, so no two threads can grab the same queue entry; the per-job
        Redis lock additionally guards against a retry/scheduled re-enqueue of
        a job another thread is still finishing. The scheduled-run tick lives
        on the dispatcher thread so it can't double-fire across workers."""
        logger.info(f"Migration worker started (max concurrent jobs: {self.max_concurrent_jobs})")

        # Scheduler tick counter: scan for due scheduled jobs every
        # `schedule_interval` seconds.
        ticks_since_schedule = 0

        with ThreadPoolExecutor(max_workers=self.max_concurrent_jobs,
                                thread_name_prefix="migrator") as executor:
            while True:
                try:
                    job, source = self._pop()

                    if job:
                        job_id = job.get("id")
                        if job_id is not None and self.queue.is_job_locked(job_id):
                            # A worker is already processing this job (a retry or
                            # scheduled re-enqueue landed while the first run was
                            # still finishing). Put the entry back so it runs once
                            # the lock is released - never run the same job twice.
                            logger.warning(f"Job {job_id} already running - deferring {source} entry")
                            if source == "scan":
                                self.queue.push_scan(job)
                            else:
                                self.queue.push_job(job)
                            time.sleep(poll_interval)
                            continue

                        logger.info(f"Processing {source} job {job_id}")
                        if job_id is not None:
                            self.queue.acquire_job_lock(job_id)
                        if not self._slots.acquire(blocking=False):
                            # Pool is full - put the entry back in Redis so it
                            # waits durably (and survives a crash) instead of
                            # sitting in the executor's in-memory queue.
                            if source == "scan":
                                self.queue.push_scan(job)
                            else:
                                self.queue.push_job(job)
                            if job_id is not None:
                                self.queue.release_job_lock(job_id)
                            time.sleep(poll_interval)
                            continue
                        queue_depth.set(self.queue.get_queue_size())
                        executor.submit(self._run_job, job, source)
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
