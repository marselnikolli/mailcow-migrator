import os
from typing import Optional

class Settings:
    # Mailcow configuration
    MAILCOW_URL: str = os.getenv("MAILCOW_URL", "http://mailcow:8080")
    MAILCOW_API_KEY: str = os.getenv("MAILCOW_API_KEY", "")
    
    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-me")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Source IMAP settings
    SOURCE_IMAP_HOST: str = os.getenv("SOURCE_IMAP_HOST", "")
    SOURCE_IMAP_PORT: int = int(os.getenv("SOURCE_IMAP_PORT", "993"))
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./mailcow.db")
    
    # Application
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    API_VERSION: str = "v1"

settings = Settings()
