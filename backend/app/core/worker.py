import time
import logging
from typing import Optional
from app.core.queue import RedisQueue
from app.core.imapsync import ImapsyncWrapper
from app.core.domains import DomainService
from app.core.mailcow import MailcowClient
from app.core.logger import StructuredLogger
from app.repositories.job_repo import JobRepository
from app.models import JobStatus

logger = logging.getLogger(__name__)

class MigrationWorker:
    def __init__(self):
        self.queue = RedisQueue()
        self.imapsync = ImapsyncWrapper()
        self.domain_service = DomainService()
        self.mailcow = MailcowClient()
        self.job_logger = StructuredLogger()
        self.max_retries = 3
    
    def process_job(self, job: dict) -> bool:
        """Process a single migration job."""
        job_id = job.get("id")
        tenant_id = job.get("tenant_id")
        source_email = job.get("source_email")
        source_password = job.get("source_password")
        target_email = job.get("target_email")
        target_password = job.get("target_password")
        source_host = job.get("source_host")
        
        try:
            self.job_logger.log_info(job_id, f"Starting migration for {source_email} -> {target_email}")
            
            # Update job status to running
            JobRepository.update_job_status(job_id, tenant_id, JobStatus.RUNNING)
            
            # Extract domain from target email
            target_domain = target_email.split("@")[1]
            
            # Ensure domain exists in Mailcow
            self.job_logger.log_info(job_id, f"Ensuring domain {target_domain} exists in Mailcow")
            try:
                self.domain_service.ensure_domain_exists(target_domain, tenant_id)
            except Exception as e:
                raise Exception(f"Failed to ensure domain: {str(e)}")
            
            # Create mailbox in Mailcow
            self.job_logger.log_info(job_id, f"Creating mailbox {target_email} in Mailcow")
            if not self.mailcow.check_mailbox_exists(target_email):
                try:
                    self.mailcow.create_mailbox(target_email, target_password)
                except Exception as e:
                    raise Exception(f"Failed to create mailbox: {str(e)}")
            
            # Run imapsync with logging
            self.job_logger.log_info(job_id, "Starting IMAP sync")
            
            def on_log(line):
                self.job_logger.log_info(job_id, line)
                self.queue.set_job_log(job_id, line)
            
            success, output = self.imapsync.run_sync_with_logging(
                source_email=source_email,
                source_password=source_password,
                target_email=target_email,
                target_password=target_password,
                on_log_callback=on_log,
                source_host=source_host
            )
            
            if success:
                self.job_logger.log_info(job_id, "Migration completed successfully")
                JobRepository.mark_job_completed(job_id, tenant_id)
                return True
            else:
                raise Exception(f"IMAP sync failed: {output}")
        
        except Exception as e:
            error_msg = str(e)
            self.job_logger.log_error(job_id, error_msg)
            
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
