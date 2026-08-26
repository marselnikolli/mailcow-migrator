import time
import logging
from typing import Optional
from app.core.queue import RedisQueue
from app.core.imapsync import CANCELLED, ImapsyncWrapper
from app.core.domains import DomainService
from app.core.mailcow import MailcowClient
from app.core.dav_sync import DavSyncer, DavSyncError
from app.core.logger import StructuredLogger
from app.repositories.job_repo import JobRepository
from app.models import JobStatus

logger = logging.getLogger(__name__)


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
        self.queue = RedisQueue()
        self.imapsync = ImapsyncWrapper()
        self.job_logger = StructuredLogger()
        self.max_retries = 3
    
    def process_job(self, job: dict) -> bool:
        """Process a single migration job."""
        job_id = job.get("id")
        tenant_id = job.get("tenant_id")
        source_email = job.get("source_email")
        source_password = job.get("source_password", "")
        target_email = job.get("target_email")
        target_password = job.get("target_password", "")
        source_host = job.get("source_host")
        source_port = job.get("source_port", 993)
        source_ssl = job.get("source_ssl", True)
        target_type = job.get("target_type", "imap")
        target_host = job.get("target_host", "localhost")
        target_port = job.get("target_port", 993)
        target_ssl = job.get("target_ssl", True)
        mailcow_url = job.get("mailcow_url")
        mailcow_api_key = job.get("mailcow_api_key")
        dry_run = job.get("dry_run", False)
        sync_calendar = job.get("sync_calendar", False)
        sync_contacts = job.get("sync_contacts", False)
        secrets = [s for s in (source_password, target_password, mailcow_api_key) if s]

        try:
            if self.queue.is_cancel_requested(job_id):
                self.job_logger.log_info(job_id, "Cancelled before processing started")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                return False

            self.job_logger.log_info(job_id, f"Starting migration for {source_email} -> {target_email}")

            if dry_run:
                self.job_logger.log_info(job_id, "DRY RUN mode: no data will be transferred, no mailboxes will be created")
            
            # Update job status to running
            JobRepository.update_job_status(job_id, tenant_id, JobStatus.RUNNING)
            
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
            
            def on_log(line):
                line = _redact(line, secrets)
                self.job_logger.log_info(job_id, line)
                self.queue.set_job_log(job_id, line)
            
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
                should_cancel=lambda: self.queue.is_cancel_requested(job_id)
            )

            if output == CANCELLED:
                self.job_logger.log_info(job_id, "Migration cancelled")
                self.queue.clear_cancel(job_id)
                JobRepository.update_job_status(job_id, tenant_id, JobStatus.CANCELLED, progress=job.get("progress", 0))
                return False

            if success:
                # Optional CalDAV/CardDAV migration (calendar + address book)
                if sync_calendar or sync_contacts:
                    if target_type != "mailcow":
                        self.job_logger.log_info(job_id, "Skipping calendar/contacts sync: target is not a Mailcow/SOGo instance")
                    else:
                        self.job_logger.log_info(job_id, f"Starting calendar/contacts sync (calendar={sync_calendar}, contacts={sync_contacts})")
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
                                dry_run=dry_run,
                            )
                            self.job_logger.log_info(job_id, f"Calendar/contacts sync done: {_redact(str(results), secrets)}")
                        except DavSyncError as e:
                            self.job_logger.log_error(job_id, f"Calendar/contacts sync failed: {_redact(str(e), secrets)}")

                if dry_run:
                    self.job_logger.log_info(job_id, "Dry run completed successfully - no data was transferred")
                else:
                    self.job_logger.log_info(job_id, "Migration completed successfully")
                JobRepository.mark_job_completed(job_id, tenant_id)
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
                return False

            # Check retry count
            retry_count = job.get("retry_count", 0)
            if retry_count < self.max_retries:
                self.job_logger.log_info(job_id, f"Retrying... (attempt {retry_count + 1}/{self.max_retries})")
                job["retry_count"] = retry_count + 1
                self.queue.push_job(job)
            else:
                self.job_logger.log_error(job_id, "Max retries exceeded, marking job as failed")
                JobRepository.mark_job_failed(job_id, tenant_id, error_msg)

            return False
    
    def start(self, poll_interval: int = 5):
        """Start the worker loop."""
        logger.info("Migration worker started")
        
        while True:
            try:
                # Pop job from queue
                job = self.queue.pop_job()
                
                if job:
                    logger.info(f"Processing job {job.get('id')}")
                    self.process_job(job)
                else:
                    # No job available, sleep briefly
                    time.sleep(poll_interval)
            
            except Exception as e:
                logger.error(f"Worker error: {str(e)}")
                time.sleep(poll_interval)

if __name__ == "__main__":
    MigrationWorker().start()
