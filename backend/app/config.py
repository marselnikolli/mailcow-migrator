import os
import secrets

_INSECURE_DEFAULT_SECRET = "your-secret-key-change-me"


class Settings:
    # Mailcow configuration
    MAILCOW_URL: str = os.getenv("MAILCOW_URL", "http://mailcow:8080")
    MAILCOW_API_KEY: str = os.getenv("MAILCOW_API_KEY", "")

    # Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # Job lock lifetime in seconds. A job held for longer than this (e.g. a
    # very large migration) can be picked up again by another worker, which is
    # safe because imapsync is idempotent. Default 12h.
    JOB_LOCK_TIMEOUT: int = int(os.getenv("JOB_LOCK_TIMEOUT", "43200"))

    # Application
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # CORS - comma-separated list of allowed origins. No wildcard default:
    # an explicit allowlist must be configured for production use.
    CORS_ORIGINS: list = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ]

    # Source IMAP settings
    SOURCE_IMAP_HOST: str = os.getenv("SOURCE_IMAP_HOST", "imap.gmail.com")
    SOURCE_IMAP_PORT: int = int(os.getenv("SOURCE_IMAP_PORT", "") or "993")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./mailcow.db")

    API_VERSION: str = "v1"

    def __init__(self):
        if not self.SECRET_KEY or self.SECRET_KEY == _INSECURE_DEFAULT_SECRET:
            if self.DEBUG:
                # Convenient for local development only: tokens won't survive
                # a restart, which is fine since nothing depends on that here.
                self.SECRET_KEY = secrets.token_urlsafe(32)
            else:
                raise RuntimeError(
                    "SECRET_KEY environment variable must be set to a random, "
                    "secret value outside of DEBUG mode. Refusing to start with "
                    "no key or the well-known default key."
                )


settings = Settings()
