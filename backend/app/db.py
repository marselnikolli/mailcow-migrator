"""Database access with SQLite (default) and PostgreSQL support.

The application layer uses the sqlite3 cursor interface (``?`` placeholders,
``cursor.lastrowid``, ``executescript``, dict-like rows). To keep that code
unchanged while allowing a Postgres backend, ``get_db()`` returns either the
native sqlite3 connection or a thin shim that adapts the sqlite3 cursor
interface to psycopg2.

Select the backend via DATABASE_URL:
  DATABASE_URL=sqlite:///./mailcow.db            (default)
  DATABASE_URL=postgresql://user:pass@host:5432/mailcow
"""

import os
import sqlite3
from typing import Optional, Dict, Any
from urllib.parse import urlparse

DATABASE_PATH = os.getenv("DATABASE_PATH", "mailcow.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATABASE_PATH}")


def is_postgres() -> bool:
    return DATABASE_URL.startswith("postgresql") or DATABASE_URL.startswith("postgres")


class _PgRow(dict):
    """A dict that also supports sqlite3.Row-style index access."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class _PgCursor:
    """psycopg2 cursor wrapped to mimic the sqlite3 cursor API used here."""

    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.rowcount = 0
        self.lastrowid = None
        self.description = None

    def _translate(self, sql: str):
        # sqlite uses '?' placeholders; postgres uses '%s'
        return sql.replace("?", "%s")

    def execute(self, sql, params=None):
        translated = self._translate(sql)
        if params is None:
            params = ()
        elif not isinstance(params, (tuple, list)):
            params = (params,)
        self.lastrowid = None
        if sql.lstrip().upper().startswith("INSERT"):
            # Use RETURNING id so we can emulate cursor.lastrowid.
            self._cur.execute(translated + " RETURNING id", params)
            row = self._cur.fetchone()
            self.lastrowid = row[0] if row else None
        else:
            self._cur.execute(translated, params)
        self.rowcount = self._cur.rowcount
        self.description = self._cur.description
        return self

    def executescript(self, script):
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self._cur.execute(self._translate(statement))
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self.description or []]
        return _PgRow(zip(cols, row))

    def fetchall(self):
        rows = self._cur.fetchall()
        cols = [d[0] for d in self.description or []] if self.description else []
        return [_PgRow(zip(cols, r)) for r in rows]

    def close(self):
        self._cur.close()


class _PgConnection:
    """psycopg2 connection wrapped to mimic the sqlite3 connection API."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def cursor(self):
        return _PgCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _connect_postgres() -> _PgConnection:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DATABASE_URL)
    return _PgConnection(conn)


def get_db():
    """Get a database connection with dict-like rows (sqlite3 or Postgres)."""
    if is_postgres():
        return _connect_postgres()
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _postgres_table_columns(conn, table: str) -> set:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """.replace("%s", "?"),
        (table,),
    )
    rows = cursor.fetchall()
    cursor.close()
    return {r["column_name"] for r in rows}


def init_db():
    """Initialize database with schema."""
    conn = get_db()
    cursor = conn.cursor()

    if is_postgres():
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'viewer',
            enabled BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, email)
        );

        CREATE TABLE IF NOT EXISTS domains (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            domain TEXT NOT NULL,
            created_in_mailcow BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, domain)
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            source_email TEXT NOT NULL,
            target_email TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES jobs(id),
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            level TEXT,
            message TEXT
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id SERIAL PRIMARY KEY,
            tenant_id INTEGER NOT NULL REFERENCES tenants(id),
            key TEXT NOT NULL UNIQUE,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.commit()
        conn.close()
        return

    # SQLite schema
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

    if is_postgres():
        existing = _postgres_table_columns(conn, "jobs")
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
            "sync_calendar": "INTEGER DEFAULT 0",
            "sync_contacts": "INTEGER DEFAULT 0",
            "sync_tasks": "INTEGER DEFAULT 0",
            "last_run_at": "TIMESTAMP",
            "last_run_status": "TEXT",
            "run_count": "INTEGER DEFAULT 0",
            "folders": "TEXT",
            "maxage_days": "INTEGER",
            "since_date": "TEXT",
            "enabled": "INTEGER DEFAULT 0",
            "schedule_interval_minutes": "INTEGER",
            "next_run_at": "TIMESTAMP",
            "scan_status": "TEXT DEFAULT 'queued'",
            "total_messages": "INTEGER DEFAULT 0",
            "copied_messages": "INTEGER DEFAULT 0",
            "total_calendar": "INTEGER DEFAULT 0",
            "calendar_copied": "INTEGER DEFAULT 0",
            "total_contacts": "INTEGER DEFAULT 0",
            "contacts_copied": "INTEGER DEFAULT 0",
            "total_tasks": "INTEGER DEFAULT 0",
            "tasks_copied": "INTEGER DEFAULT 0",
            "expected_total": "INTEGER DEFAULT 0",
            "eta_seconds": "INTEGER",
        }
        for column, definition in migrations.items():
            if column not in existing:
                cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")
        conn.commit()
        conn.close()
        return

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
        "sync_calendar": "INTEGER DEFAULT 0",
        "sync_contacts": "INTEGER DEFAULT 0",
        "sync_tasks": "INTEGER DEFAULT 0",
        "last_run_at": "TIMESTAMP",
        "last_run_status": "TEXT",
        "run_count": "INTEGER DEFAULT 0",
        "folders": "TEXT",
        "maxage_days": "INTEGER",
        "since_date": "TEXT",
        "enabled": "INTEGER DEFAULT 0",
        "schedule_interval_minutes": "INTEGER",
        "next_run_at": "TIMESTAMP",
        "scan_status": "TEXT DEFAULT 'queued'",
        "total_messages": "INTEGER DEFAULT 0",
        "copied_messages": "INTEGER DEFAULT 0",
        "total_calendar": "INTEGER DEFAULT 0",
        "calendar_copied": "INTEGER DEFAULT 0",
        "total_contacts": "INTEGER DEFAULT 0",
        "contacts_copied": "INTEGER DEFAULT 0",
        "total_tasks": "INTEGER DEFAULT 0",
        "tasks_copied": "INTEGER DEFAULT 0",
        "expected_total": "INTEGER DEFAULT 0",
        "eta_seconds": "INTEGER",
    }

    for column, definition in migrations.items():
        if column not in existing:
            cursor.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

    conn.commit()
    conn.close()


def backfill_encrypted_secrets():
    """Encrypt any secrets still stored as plaintext (rows created before
    secret-at-rest encryption was introduced)."""
    from app.core.secrets import SecretEncryptor
    secrets = SecretEncryptor()
    conn = get_db()
    cursor = conn.cursor()

    for column in ("source_password", "target_password", "mailcow_api_key"):
        rows = cursor.execute(f"SELECT id, {column} AS value FROM jobs WHERE {column} IS NOT NULL AND {column} != ''").fetchall()
        for row in rows:
            value = row["value"]
            if not secrets.is_encrypted(value):
                cursor.execute(
                    f"UPDATE jobs SET {column} = ? WHERE id = ?",
                    (secrets.encrypt(value), row["id"]),
                )

    conn.commit()
    conn.close()


def dict_from_row(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    """Convert a row (sqlite3.Row or _PgRow) to a plain dict."""
    if row is None:
        return None
    return dict(row)