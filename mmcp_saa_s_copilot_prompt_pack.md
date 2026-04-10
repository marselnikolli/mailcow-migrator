# 🚀 MMCP SaaS — Copilot Prompt Pack (Full Build Instructions)

This file contains **copy-paste prompts for GitHub Copilot** to generate the entire Mail Migration SaaS platform step-by-step.

Use each prompt inside the corresponding file in VS Code.

---

# 🟦 PHASE 0 — BOOTSTRAP

## 📁 docker-compose.yml
**Prompt:**
> Create a Docker Compose setup with the following services:
> - backend (FastAPI, port 8000)
> - frontend (React/Vite, port 3000)
> - redis (latest)
>
> Ensure proper networking between services.

---

## 📁 backend/app/main.py
**Prompt:**
> Create a FastAPI application entrypoint.
> Include:
> - FastAPI instance
> - health check endpoint `/health`
> - router registration system for modular routes

---

## 📁 backend/app/config.py
**Prompt:**
> Create a config module that loads environment variables using os.getenv.
> Include:
> - MAILCOW_URL
> - MAILCOW_API_KEY
> - REDIS_URL
> - SECRET_KEY
> - SOURCE_IMAP settings

---

## 📁 frontend/src/main.tsx
**Prompt:**
> Create React Vite entry point with TailwindCSS.
> Setup router with pages:
> - Dashboard
> - Login
> - Domains
> - Jobs

---

# 🟩 PHASE 1 — MULTI-TENANT CORE

## 📁 backend/app/db.py
**Prompt:**
> Create SQLite database connection layer.
> Include get_db() and init_db() functions.
> Ensure connection row_factory returns dict-like rows.

---

## 📁 backend/app/models.py
**Prompt:**
> Create SQLite schema initialization for SaaS system.
> Tables:
> - tenants
> - users
> - domains
> - jobs
> - logs
> - api_keys
> Include relationships via tenant_id.

---

## 📁 backend/app/middleware/tenant.py
**Prompt:**
> Create FastAPI middleware that extracts tenant_id from header `X-Tenant-ID`.
> Attach tenant_id to request.state.

---

## 📁 backend/app/repositories/job_repo.py
**Prompt:**
> Create repository layer for jobs.
> Include:
> - create_job
> - update_job_status
> - get_jobs_by_tenant
> Ensure all queries filter by tenant_id.

---

# 🟨 PHASE 2 — AUTH SYSTEM

## 📁 backend/app/auth.py
**Prompt:**
> Implement authentication system using JWT.
> Include:
> - password hashing with bcrypt
> - token generation
> - token validation
> - role support (owner/admin/operator/viewer)

---

## 📁 backend/app/routes/auth.py
**Prompt:**
> Create FastAPI auth routes:
> - POST /auth/register
> - POST /auth/login
> - GET /auth/me
> Use JWT authentication and return access tokens.

---

## 📁 backend/app/deps/roles.py
**Prompt:**
> Create role-based access dependency for FastAPI.
> Function require_role(roles: list) that blocks unauthorized users.

---

# 🟧 PHASE 3 — MAILCOW INTEGRATION

## 📁 backend/app/core/mailcow.py
**Prompt:**
> Create Mailcow API client.
> Implement:
> - create_mailbox(email, password)
> - check_mailbox_exists(email)
> - create_domain(domain)
> Use requests and API key header authentication.

---

## 📁 backend/app/core/domains.py
**Prompt:**
> Create service that ensures domain exists in Mailcow.
> If not found, automatically create it with default quota settings.

---

# 🟥 PHASE 4 — IMAPSYNC WORKER

## 📁 backend/app/core/imapsync.py
**Prompt:**
> Create wrapper for imapsync command execution.
> Must support:
> - SSL connections
> - logging output
> - success/failure return boolean

---

## 📁 backend/app/core/worker.py
**Prompt:**
> Create background worker that processes migration jobs.
> Features:
> - fetch job from Redis queue
> - create mailbox in Mailcow
> - run imapsync
> - update SQLite job status
> - retry failed jobs up to 3 times

---

## 📁 backend/app/core/queue.py
**Prompt:**
> Implement Redis queue system for job processing.
> Include:
> - push_job(job)
> - pop_job()
> - job locking mechanism

---

# 🟪 PHASE 5 — API ROUTES

## 📁 backend/app/routes/jobs.py
**Prompt:**
> Create FastAPI routes for job management.
> Include:
> - POST /jobs/create
> - GET /jobs/list
> - POST /jobs/retry/{job_id}
> Ensure tenant isolation.

---

## 📁 backend/app/routes/domains.py
**Prompt:**
> Create domain management routes:
> - add domain
> - list domains
> - validate domain exists in Mailcow

---

## 📁 backend/app/routes/logs.py
**Prompt:**
> Create log streaming API.
> Support:
> - fetching logs by job_id
> - WebSocket endpoint for real-time logs

---

# 🟫 PHASE 6 — FRONTEND (SAAS UI)

## 📁 frontend/src/pages/Dashboard.tsx
**Prompt:**
> Create SaaS dashboard UI.
> Include:
> - stats cards (active, failed, completed jobs)
> - recent jobs table
> - live logs widget

---

## 📁 frontend/src/pages/Domains.tsx
**Prompt:**
> Create domain management UI.
> Features:
> - list domains
> - add domain form
> - migration status per domain

---

## 📁 frontend/src/pages/Jobs.tsx
**Prompt:**
> Create job listing UI.
> Include:
> - filter by status
> - retry button
> - progress indicators

---

## 📁 frontend/src/components/LiveLogs.tsx
**Prompt:**
> Create WebSocket-based live log viewer.
> Connect to backend WS endpoint and stream logs in real-time.

---

## 📁 frontend/src/api.ts
**Prompt:**
> Create Axios API wrapper.
> Include:
> - JWT authentication headers
> - tenant header injection (X-Tenant-ID)
> - base URL configuration

---

# 🟦 PHASE 7 — OBSERVABILITY

## 📁 backend/app/core/logger.py
**Prompt:**
> Create structured logging system.
> Log:
> - job events
> - worker status
> - errors
> Save logs into SQLite logs table.

---

# 🟩 PHASE 8 — DEPLOYMENT

## 📁 Dockerfile (backend)
**Prompt:**
> Create production Dockerfile for FastAPI backend.
> Must include:
> - Python slim image
> - installation of imapsync
> - environment variable support

---

## 📁 Dockerfile (frontend)
**Prompt:**
> Create Dockerfile for React Vite app.
> Build production static files and serve with nginx.

---

# 🟨 FINAL INSTRUCTION

## SYSTEM-WIDE COPILOT RULE
**Use this everywhere:**
> Always ensure tenant isolation by filtering all database queries using tenant_id.

---

# 🚀 END OF PROMPT PACK

This pack allows Copilot to generate the entire SaaS platform file-by-file with minimal manual coding.

