import sqlite3
from typing import Optional, Dict, Any
import os

DATABASE_PATH = os.getenv("DATABASE_PATH", "mailcow.db")

def get_db():
    """Get database connection with dict-like rows."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database with schema."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        enabled BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        email TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'viewer',
        enabled BOOLEAN DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        UNIQUE(tenant_id, email)
    );
    
    CREATE TABLE IF NOT EXISTS domains (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        domain TEXT NOT NULL,
        created_in_mailcow BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id),
        UNIQUE(tenant_id, domain)
    );
    
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        source_email TEXT NOT NULL,
        target_email TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    );
    
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        level TEXT,
        message TEXT,
        FOREIGN KEY (job_id) REFERENCES jobs(id)
    );
    
    CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id INTEGER NOT NULL,
        key TEXT NOT NULL UNIQUE,
        name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
    );
    """)
    
    conn.commit()
    conn.close()

def migrate_schema():
    """Add columns added after the initial release (idempotent)."""
    conn = get_db()
    cursor = conn.cursor()

    existing = {row["name"] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()}

    migrations = {
        "source_password": "TEXT",
        "target_password": "TEXT",
        "source_host": "TEXT DEFAULT 'imap.gmail.com'",
        "source_port": "INTEGER DEFAULT 993",
        "source_ssl": "INTEGER DEFAULT 1",
        "target_type": "TEXT DEFAULT 'imap'",
        "target_host": "TEXT DEFAULT 'localhost'",
        "target_port": "INTEGER DEFAULT 993",
        "target_ssl": "INTEGER DEFAULT 1",
        "mailcow_url": "TEXT",
        "mailcow_api_key": "TEXT",
        "dry_run": "INTEGER DEFAULT 0",
    }

    for column, definition in migrations.items():
        if column not in existing:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

    conn.commit()
    conn.close()

def dict_from_row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    """Convert sqlite3.Row to dictionary."""
    if row is None:
        return None
    return dict(row)
