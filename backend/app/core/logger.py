import logging
from datetime import datetime
from app.db import get_db
from enum import Enum

logger = logging.getLogger(__name__)

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

class StructuredLogger:
    def __init__(self):
        self.db = None
    
    def _log(self, job_id: int, level: str, message: str):
        """Log message to database and console."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO logs (job_id, level, message, timestamp)
            VALUES (?, ?, ?, ?)
        """, (job_id, level, message, datetime.now()))
        
        conn.commit()
        conn.close()
        
        # Also log to console
        log_func = {
            "debug": logger.debug,
            "info": logger.info,
            "warning": logger.warning,
            "error": logger.error
        }.get(level, logger.info)
        
        log_func(f"[Job {job_id}] {message}")
    
    def log_debug(self, job_id: int, message: str):
        """Log debug message."""
        self._log(job_id, LogLevel.DEBUG.value, message)
    
    def log_info(self, job_id: int, message: str):
        """Log info message."""
        self._log(job_id, LogLevel.INFO.value, message)
    
    def log_warning(self, job_id: int, message: str):
        """Log warning message."""
        self._log(job_id, LogLevel.WARNING.value, message)
    
    def log_error(self, job_id: int, message: str):
        """Log error message."""
        self._log(job_id, LogLevel.ERROR.value, message)
    
    def get_job_logs(self, job_id: int, level: str = None) -> list:
        """Retrieve logs for a job."""
        conn = get_db()
        cursor = conn.cursor()
        
        if level:
            cursor.execute("""
                SELECT timestamp, level, message FROM logs 
                WHERE job_id = ? AND level = ?
                ORDER BY timestamp ASC
            """, (job_id, level))
        else:
            cursor.execute("""
                SELECT timestamp, level, message FROM logs 
                WHERE job_id = ?
                ORDER BY timestamp ASC
            """, (job_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for row in rows:
            logs.append({
                "timestamp": row[0],
                "level": row[1],
                "message": row[2]
            })
        
        return logs
    
    def clear_job_logs(self, job_id: int):
        """Clear logs for a job."""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
        
        conn.commit()
        conn.close()
