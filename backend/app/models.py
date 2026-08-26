from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum

# Enums
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

# Database Models
class Tenant(BaseModel):
    id: Optional[int] = None
    name: str
    enabled: bool = True
    created_at: Optional[datetime] = None

class User(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    email: EmailStr
    password_hash: Optional[str] = None
    role: UserRole = UserRole.VIEWER
    enabled: bool = True
    created_at: Optional[datetime] = None

class Domain(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    domain: str
    created_in_mailcow: bool = False
    created_at: Optional[datetime] = None

class Job(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    source_email: str
    target_email: str
    source_password: Optional[str] = None
    target_password: Optional[str] = None
    source_host: Optional[str] = None
    source_port: Optional[int] = 993
    source_ssl: Optional[bool] = True
    target_type: Optional[str] = "imap"
    target_host: Optional[str] = None
    target_port: Optional[int] = 993
    target_ssl: Optional[bool] = True
    mailcow_url: Optional[str] = None
    mailcow_api_key: Optional[str] = None
    dry_run: Optional[bool] = False
    sync_calendar: Optional[bool] = False
    sync_contacts: Optional[bool] = False
    status: JobStatus = JobStatus.PENDING
    progress: int = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class Log(BaseModel):
    id: Optional[int] = None
    job_id: int
    timestamp: Optional[datetime] = None
    level: LogLevel
    message: str

class APIKey(BaseModel):
    id: Optional[int] = None
    tenant_id: int
    key: str
    name: Optional[str] = None
    created_at: Optional[datetime] = None

# API Request/Response Models
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.VIEWER

class ServerConfig(BaseModel):
    host: str = "imap.gmail.com"
    port: int = 993
    ssl: bool = True

class JobCreate(BaseModel):
    source_email: str
    target_email: Optional[str] = None
    source_password: str = ""
    target_password: str = ""
    source_server: ServerConfig = ServerConfig()
    target_type: str = "imap"
    target_server: ServerConfig = ServerConfig(host="localhost")
    mailcow_url: str = None
    mailcow_api_key: str = None
    dry_run: bool = False
    sync_calendar: bool = False
    sync_contacts: bool = False

class BulkJobCreate(BaseModel):
    jobs: List[JobCreate]

class JobUpdate(BaseModel):
    """Fields editable on a job while it's still pending (not yet picked up
    by a worker). Anything left as None is left unchanged."""
    target_email: Optional[str] = None
    target_password: Optional[str] = None
    target_type: Optional[str] = None
    target_server: Optional[ServerConfig] = None
    mailcow_url: Optional[str] = None
    mailcow_api_key: Optional[str] = None
    dry_run: Optional[bool] = None
    sync_calendar: Optional[bool] = None
    sync_contacts: Optional[bool] = None

class ImportedAccount(BaseModel):
    email: str
    password: str

class ImportPreviewResponse(BaseModel):
    total: int
    accounts: List[ImportedAccount]

class JobResponse(BaseModel):
    id: int
    status: JobStatus
    progress: int
    source_email: str
    target_email: str
    source_host: Optional[str] = None
    target_type: Optional[str] = "imap"
    target_host: Optional[str] = None
    dry_run: Optional[bool] = False
    sync_calendar: Optional[bool] = False
    sync_contacts: Optional[bool] = False
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class DomainCreate(BaseModel):
    domain: str
