from typing import List, Optional
from app.db import get_db, dict_from_row
from app.models import Job, JobStatus
from datetime import datetime

class JobRepository:
    @staticmethod
    def create_job(tenant_id: int, source_email: str, target_email: str,
                   source_password: str = "", target_password: str = "",
                   source_host: str = None, source_port: int = 993, source_ssl: bool = True,
                   target_type: str = "imap", target_host: str = None,
                   target_port: int = 993, target_ssl: bool = True,
                   mailcow_url: str = None, mailcow_api_key: str = None,
                   dry_run: bool = False) -> Job:
        """Create a new job."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO jobs (
                tenant_id, source_email, target_email,
                source_password, target_password,
                source_host, source_port, source_ssl,
                target_type, target_host, target_port, target_ssl,
                mailcow_url, mailcow_api_key, dry_run,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant_id, source_email, target_email,
            source_password, target_password,
            source_host, source_port, int(source_ssl),
            target_type, target_host, target_port, int(target_ssl),
            mailcow_url, mailcow_api_key, int(dry_run),
            JobStatus.PENDING.value
        ))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return Job(
            id=job_id,
            tenant_id=tenant_id,
            source_email=source_email,
            target_email=target_email,
            source_password=source_password,
            target_password=target_password,
            source_host=source_host,
            source_port=source_port,
            source_ssl=source_ssl,
            target_type=target_type,
            target_host=target_host,
            target_port=target_port,
            target_ssl=target_ssl,
            mailcow_url=mailcow_url,
            mailcow_api_key=mailcow_api_key,
            dry_run=dry_run,
            status=JobStatus.PENDING
        )
    
    @staticmethod
    def update_job_status(job_id: int, tenant_id: int, status: JobStatus, 
                         progress: int = 0, error_message: Optional[str] = None) -> bool:
        """Update job status and progress."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE jobs 
            SET status = ?, progress = ?, error_message = ?
            WHERE id = ? AND tenant_id = ?
        """, (status.value, progress, error_message, job_id, tenant_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    @staticmethod
    def get_job_by_id(job_id: int, tenant_id: int) -> Optional[Job]:
        """Get a job by ID with tenant isolation."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM jobs WHERE id = ? AND tenant_id = ?
        """, (job_id, tenant_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            row_dict = dict_from_row(row)
            row_dict["source_ssl"] = bool(row_dict.get("source_ssl"))
            row_dict["target_ssl"] = bool(row_dict.get("target_ssl"))
            row_dict["dry_run"] = bool(row_dict.get("dry_run"))
            return Job(**row_dict)
        return None
    
    @staticmethod
    def get_jobs_by_tenant(tenant_id: int, status: Optional[JobStatus] = None, 
                          limit: int = 100, offset: int = 0) -> List[Job]:
        """Get jobs for a tenant with optional status filter."""
        conn = get_db()
        cursor = conn.cursor()
        
        if status:
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE tenant_id = ? AND status = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (tenant_id, status.value, limit, offset))
        else:
            cursor.execute("""
                SELECT * FROM jobs 
                WHERE tenant_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
            """, (tenant_id, limit, offset))
        
        rows = cursor.fetchall()
        conn.close()
        
        jobs = []
        for row in rows:
            row_dict = dict_from_row(row)
            row_dict["source_ssl"] = bool(row_dict.get("source_ssl"))
            row_dict["target_ssl"] = bool(row_dict.get("target_ssl"))
            row_dict["dry_run"] = bool(row_dict.get("dry_run"))
            jobs.append(Job(**row_dict))
        return jobs
    
    @staticmethod
    def update_job(job_id: int, tenant_id: int, **fields) -> bool:
        """Update arbitrary columns on a job. Only intended for editing jobs
        that are still pending (enforced by the caller)."""
        if not fields:
            return False

        set_clause = ", ".join(f"{column} = ?" for column in fields)
        values = list(fields.values()) + [job_id, tenant_id]

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE jobs SET {set_clause} WHERE id = ? AND tenant_id = ?",
            values,
        )
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    @staticmethod
    def delete_job(job_id: int, tenant_id: int) -> bool:
        """Delete a job and its logs."""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
        cursor.execute("DELETE FROM jobs WHERE id = ? AND tenant_id = ?", (job_id, tenant_id))

        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success

    @staticmethod
    def mark_job_completed(job_id: int, tenant_id: int) -> bool:
        """Mark job as completed."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE jobs 
            SET status = ?, completed_at = ?, progress = 100
            WHERE id = ? AND tenant_id = ?
        """, (JobStatus.COMPLETED.value, datetime.now(), job_id, tenant_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
    
    @staticmethod
    def mark_job_failed(job_id: int, tenant_id: int, error: str) -> bool:
        """Mark job as failed."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE jobs 
            SET status = ?, error_message = ?
            WHERE id = ? AND tenant_id = ?
        """, (JobStatus.FAILED.value, error, job_id, tenant_id))
        
        conn.commit()
        success = cursor.rowcount > 0
        conn.close()
        return success
