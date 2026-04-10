from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum

# Enums
class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

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

class JobCreate(BaseModel):
    source_email: str
    target_email: str
    domain: str

class JobResponse(BaseModel):
    id: int
    status: JobStatus
    progress: int
    source_email: str
    target_email: str
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

class DomainCreate(BaseModel):
    domain: str
