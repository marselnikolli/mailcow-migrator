from typing import List, Optional
from app.db import get_db, dict_from_row
from app.models import Job, JobStatus
from datetime import datetime

class JobRepository:
    @staticmethod
    def create_job(tenant_id: int, source_email: str, target_email: str) -> Job:
        """Create a new job."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO jobs (tenant_id, source_email, target_email, status)
            VALUES (?, ?, ?, ?)
        """, (tenant_id, source_email, target_email, JobStatus.PENDING.value))
        
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return Job(
            id=job_id,
            tenant_id=tenant_id,
            source_email=source_email,
            target_email=target_email,
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
            jobs.append(Job(**row_dict))
        return jobs
    
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
