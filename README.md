# mailcow Mail Migration Platform

A multi-tenant email migration platform that migrates mailboxes **into Mailcow** from any IMAP source — including email (IMAP), calendar (CalDAV), address book (CardDAV) and tasks (VTODO). Built with FastAPI + React.

## Features

- **Multi-tenant SaaS** — tenant isolation via scoped JWT, role-based access (owner / admin / operator / viewer)
- **Email migration** — imapsync wrapper, folder / date-range filters, resume-safe idempotent runs
- **Calendar & contacts** — CalDAV (calendar + tasks) and CardDAV (address book) sync into Mailcow + SOGo
- **Auto-provisioning** — creates the destination domain + mailbox in Mailcow via its API before migrating
- **Dry run** — validates connectivity, counts what would be transferred, creates nothing
- **Live progress** — per-folder progress and ETA parsed from imapsync output
- **Recurring delta sync** — schedule jobs to re-run on an interval for pre-cutover warm-up
- **Reports** — per-job summary (messages/folders) with CSV export
- **Estimates** — probe the source mailbox for folder/message counts before migrating
- **IMAP autodiscovery** — best-effort source server detection from SRV / common hostnames / MX
- **Notifications** — webhook and/or SMTP email on job completion, failure or cancel
- **Metrics** — Prometheus `/metrics` endpoint (queue depth, jobs by outcome, copied messages, durations)
- **Secrets at rest** — mailbox passwords and Mailcow API keys are Fernet-encrypted in the database and queue
- **Modern UI** — React 18 / Vite / TailwindCSS, real-time logs over WebSocket

## Architecture

```
Browser ──► Frontend (nginx, :4301) ──► Backend API (FastAPI, :4300) ──► Redis queue
                                              │                            │
                                              ▼                            ▼
                                         SQLite / Postgres            Worker (imapsync + DAV sync)
```

- **Backend**: FastAPI, SQLite (default) or PostgreSQL, Redis queue, `imapsync`
- **Frontend**: React 18, Vite, TailwindCSS, Axios, WebSocket log streaming
- **Worker**: separate container running `app.core.worker`, pulls jobs from Redis, executes imapsync and the DAV sync

## Getting Started

### Prerequisites

- Docker & Docker Compose
- A Mailcow instance with the API enabled (create an API key in Mailcow's UI)

### Install & Run

```bash
cp .env.example .env
# edit .env: MAILCOW_URL, MAILCOW_API_KEY, SECRET_KEY (see below)

# development (docker-compose.yml)
docker compose up --build

# production (docker-compose.prod.yml — includes the worker service)
docker compose -f docker-compose.prod.yml up -d --build
```

### Access

| Service   | URL                      |
|-----------|--------------------------|
| Frontend  | http://localhost:4301    |
| API       | http://localhost:4300    |
| API docs  | http://localhost:4300/docs |
| Metrics   | http://localhost:4300/metrics |
| Health    | http://localhost:4300/health |

> The prod compose runs a dedicated **worker** service; the dev compose shares the backend container. In both, the backend and worker share the `./backend` volume so they use the same database and code.

### First Run

1. Open the frontend and **Register** a new account (creates a tenant; keep the tenant ID).
2. Go to **Jobs → Create Job**.
3. Enter the source account (email + password), pick destination type **Mailcow (API)**, set the Mailcow URL + API key.
4. Optionally enable **Calendar / Contacts / Tasks**, set **folder / date filters**, or turn on **Recurring delta sync**.
5. Create the job. The worker auto-provisions the mailbox on Mailcow, then runs imapsync (+ DAV sync if enabled).

> **Dry run** mode validates connectivity and reports what would be transferred without creating anything. A real run auto-creates the destination mailbox via the Mailcow API — so a dry run against a not-yet-existing mailbox will report an authentication failure on the destination until you run once for real.

## Configuration

All settings live in `.env` (see `.env.example`).

| Variable | Description |
|----------|-------------|
| `MAILCOW_URL` | Mailcow base URL |
| `MAILCOW_API_KEY` | Mailcow API key (used for auto-provisioning) |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing key (required outside `DEBUG`); also derives the secret-encryption key |
| `DEBUG` | `True`/`False` |
| `CORS_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `DATABASE_PATH` / `DATABASE_URL` | `mailcow.db` (SQLite) or a `postgresql://…` URL |
| `SOURCE_IMAP_HOST` / `SOURCE_IMAP_PORT` | Default IMAP server used when autodiscovery finds nothing |
| `JOB_LOCK_TIMEOUT` | Queue lock lifetime in seconds (default `43200` = 12h) |
| `NOTIFY_WEBHOOK_URL` | Optional webhook URL, POSTed JSON on job events |
| `NOTIFY_EMAIL_TO` / `NOTIFY_EMAIL_FROM` | Optional email notification recipients |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_STARTTLS` | SMTP settings for notifications |

### Seeded admin (for local dev)

Run `python scripts/seed_admin.py` inside the backend container to create the default admin:

- Email: `admin@example.com`
- Password: `admin123`
- Tenant ID: `1`

## Running the Worker

In production the worker runs as its own container. To run it directly:

```bash
cd backend
python -m app.core.worker
```

The worker polls the Redis queue, processes jobs, and re-queues enabled scheduled jobs when due.

## API Overview

### Auth

- `POST /api/v1/auth/register` — register a new tenant + owner
- `POST /api/v1/auth/login` — login, returns a JWT (set tenant id in the body)
- `GET /api/v1/auth/me` — current user info

### Jobs (all require `Authorization: Bearer <token>`)

- `POST /api/v1/jobs/create` — create a job
- `POST /api/v1/jobs/bulk-create` — create many jobs at once
- `POST /api/v1/jobs/import-preview` — parse an uploaded CSV/XLSX/JSON account list
- `GET /api/v1/jobs/list` — list jobs (optional `?status=` filter)
- `GET /api/v1/jobs/{id}` — job details
- `PUT /api/v1/jobs/{id}` — edit a pending/failed job's destination
- `POST /api/v1/jobs/retry/{id}` — re-queue a failed job
- `POST /api/v1/jobs/{id}/cancel` — cancel a pending/running job
- `DELETE /api/v1/jobs/{id}` — delete a job and its logs
- `GET /api/v1/jobs/{id}/report` — structured migration report (from the log)
- `GET /api/v1/jobs/{id}/report.csv` — CSV export of the report
- `GET /api/v1/jobs/{id}/estimate` — source mailbox estimate (folder/message counts)
- `GET /api/v1/jobs/autodiscover/{email}` — best-effort source IMAP server discovery

### Domains

- `POST /api/v1/domains/add` — add a domain
- `GET /api/v1/domains/list` — list domains
- `GET /api/v1/domains/validate/{domain}` — validate a domain in Mailcow

### Logs

- `GET /api/v1/logs/{job_id}` — job logs
- `WS /api/v1/logs/ws/{job_id}` — real-time logs (JWT sent as first frame)

## Testing

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
```

## Project Structure

```
mailcow-migrator/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app
│   │   ├── config.py          # Settings
│   │   ├── db.py              # SQLite / Postgres access + schema
│   │   ├── auth.py            # JWT auth
│   │   ├── models.py          # Pydantic models
│   │   ├── routes/            # auth, jobs, domains, logs
│   │   ├── core/              # worker, imapsync, dav_sync, mailcow, queue,
│   │   │                      #   secrets, notifications, metrics, report,
│   │   │                      #   estimate, autodiscover, imapsync_progress
│   │   ├── repositories/      # data access
│   │   └── deps/roles.py      # auth/role dependencies
│   ├── scripts/seed_admin.py  # local dev admin seeding
│   ├── tests/                 # pytest suite
│   └── requirements*.txt
├── frontend/
│   └── src/                   # React app (pages, components, api.ts)
├── docker-compose.yml         # dev compose
├── docker-compose.prod.yml    # prod compose (adds worker, healthcheck)
└── .env.example               # environment template
```

## Database

SQLite by default (`mailcow.db`). For PostgreSQL, set `DATABASE_URL` and run with a Postgres instance; the schema and migrations are created automatically on startup. Tables: `tenants`, `users`, `domains`, `jobs`, `logs`, `api_keys`.

## Security Notes

- Secrets are encrypted at rest (Fernet, key derived from `SECRET_KEY`); existing plaintext rows are backfilled on startup.
- JWT required on all tenant-scoped endpoints; tenant identity comes from the verified token, never client headers.
- `mailcow_url` is validated to reject private/internal targets (SSRF guard).
- Use a strong random `SECRET_KEY` in production: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Support

For issues or feature requests, open an issue in the repository.
