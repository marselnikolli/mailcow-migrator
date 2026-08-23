# Code Audit — mailcow-migrator

Scope: full backend (`backend/app/**`) and frontend (`frontend/src/**`), plus the uncommitted working-tree diff. Focus: security, correctness, and code quality.

**Status: all findings below have been fixed** (see "Remediation" under each). Verified against the live `docker compose` stack: unauthenticated/spoofed-tenant requests now 401, tenant data stays isolated per JWT, `/auth/me` and the logs WebSocket work without tokens in the URL, SSRF to `169.254.169.254`/private ranges is rejected with 400, CORS accepts the real frontend origin and rejects others, and a missing/default `SECRET_KEY` outside `DEBUG` now refuses to start.

## Summary

The application (FastAPI + SQLite + Redis queue + `imapsync`, React/Vite frontend) has good bones in a few places — all SQL is parameterized, passwords are hashed with bcrypt, and shell commands are built as argv lists rather than shell strings. However, there is one **critical** gap: none of the tenant-scoped API routes actually enforce authentication, which undermines most of the other security work in the codebase. There is also a concrete SSRF and a hardcoded default JWT secret.

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | No authentication/authorization enforced on jobs, domains, logs APIs | **Critical** | ✅ Fixed |
| 2 | SSRF via attacker-controlled `mailcow_url` on job creation | **High** | ✅ Fixed |
| 3 | JWT `SECRET_KEY` defaults to a hardcoded, publicly-known string | **High** | ✅ Fixed |
| 4 | JWT sent as a URL query parameter (`/auth/me`, logs WebSocket) | Medium | ✅ Fixed |
| 5 | Permissive CORS (`allow_origins=["*"]` with `allow_credentials=True`) | Low | ✅ Fixed |
| 6 | Dead/unwired authorization code (`require_role`) | Low (code quality) | ✅ Fixed |
| 7 | Frontend/backend contract mismatch on `/auth/me` | Low (bug) | ✅ Fixed |

---

## 1. Critical — No authentication is actually enforced

**Files:** `backend/app/routes/jobs.py`, `backend/app/routes/domains.py`, `backend/app/routes/logs.py`, `backend/app/middleware/tenant.py`, `backend/app/deps/roles.py`

`app/deps/roles.py` defines a `require_role()` dependency that validates the `Authorization: Bearer <jwt>` header and attaches `request.state.tenant_id` from the verified token. **It is never used.** A repo-wide search confirms zero `Depends(...)` calls anywhere in the router files:

```
$ grep -rn "require_role\|Depends(" backend/app/routes/ backend/app/main.py
(no matches)
```

Instead, every route reads `request.state.tenant_id`, which is populated exclusively by `TenantMiddleware` from the **client-supplied `X-Tenant-ID` header** — no token, password, or session check involved:

```python
# backend/app/middleware/tenant.py
tenant_id = request.headers.get("X-Tenant-ID")
...
request.state.tenant_id = int(tenant_id) if tenant_id.isdigit() else tenant_id
```

Net effect: anyone who can reach the API can set `X-Tenant-ID: 1` (or iterate small integers) and, with no credentials at all:

- List, read, and create migration jobs for any tenant (`POST /api/v1/jobs/create`, `GET /api/v1/jobs/list`, `GET /api/v1/jobs/{id}`), including source/target hostnames, dry-run flags, and error messages.
- Read and add domains for any tenant (`GET/POST /api/v1/domains/*`).
- Read job logs, including real-time logs over the unauthenticated WebSocket (`GET /api/v1/logs/{id}`, `WS /api/v1/logs/ws/{id}`).

The frontend does send a Bearer token (see `frontend/src/api.ts`), but it's decorative — the backend never checks it on these routes, so the token provides no actual protection.

**Fix:** Wire `require_role(...)` (or an equivalent `get_current_user` dependency) into every router in `jobs.py`, `domains.py`, and `logs.py`, and derive `tenant_id` from the verified JWT rather than the `X-Tenant-ID` header. If the header is kept at all, it should only be used for context/logging, never as the authorization boundary.

**Remediation:** `app/deps/roles.py` now exposes `get_current_user`, which validates the `Authorization: Bearer <jwt>` header and sets `request.state.{user_id,tenant_id,role}` from the verified token. It's applied at the router level (`APIRouter(dependencies=[Depends(get_current_user)])`) in `jobs.py` and `domains.py`, and per-route in `logs.py`, so every HTTP endpoint on these routers now requires a valid token. `TenantMiddleware` and the `X-Tenant-ID`-as-authorization pattern were removed entirely (`backend/app/middleware/tenant.py` deleted, `main.py` updated). While fixing this, a second, previously-latent bug surfaced: `AuthService.create_token_response` stored the JWT `sub` claim as an int, and `python-jose` rejects non-string `sub` claims on decode — so `decode_token` always silently returned `None`. Since `require_role` was dead code before, this never showed up; now that auth is actually enforced, it was fixed too (`sub` is stored as `str(user_id)` and cast back to `int` on read).

---

## 2. High — SSRF via `mailcow_url`

**Files:** `backend/app/models.py` (`JobCreate.mailcow_url`), `backend/app/core/worker.py`, `backend/app/core/mailcow.py`

`JobCreate.mailcow_url` is a free-form string supplied by the API caller and is used, unvalidated, as the base URL for outbound HTTP requests:

```python
# backend/app/core/mailcow.py
def __init__(self, base_url: str = None, api_key: str = None):
    self.base_url = base_url or settings.MAILCOW_URL
    ...
def _make_request(self, method, endpoint, data=None):
    url = f"{self.base_url}/api/v1/{endpoint}"
    response = requests.get(url, headers=self.headers)   # or post/put/delete
```

Because this is only reachable through `create_job`/`bulk_create_jobs` (unauthenticated per finding #1), any caller can set `mailcow_url` to an internal address (e.g. a cloud metadata endpoint, an internal admin service, or `http://127.0.0.1:<port>`) and cause the backend worker to issue GET/POST/PUT/DELETE requests — with a JSON body it also controls (`create_mailbox`/`create_domain` payloads) — to that host. This is a full host+protocol SSRF, not just a path/query one.

**Fix:** Validate `mailcow_url` against an allowlist of configured Mailcow instances (or drop the per-job override entirely and always use `settings.MAILCOW_URL`), and/or resolve and block requests to private/link-local IP ranges before issuing them.

**Remediation:** Added `backend/app/core/security.py::validate_public_url`, which parses the URL, requires `http`/`https`, resolves the hostname, and rejects it if any resolved address is private/loopback/link-local/multicast/reserved/unspecified (covers RFC1918, `127.0.0.0/8`, `169.254.169.254`, etc.). `jobs.py` calls this on `mailcow_url` in both `create_job` and `bulk_create_jobs` before the job is persisted or queued, returning 400 on rejection. Verified live: `mailcow_url: http://169.254.169.254` now returns `400 {"detail":"mailcow_url resolves to a non-public address ..."}`, while a normal job creation still succeeds. This is best-effort (DNS can change between validation and the worker's actual request), which is called out in the code comment.

---

## 3. High — Hardcoded default JWT secret

**File:** `backend/app/config.py:13`

```python
SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-change-me")
```

If `SECRET_KEY` is not set in the deployment environment, every JWT is signed with a well-known literal string. Anyone can forge a token for any `user_id`/`tenant_id`/`role` (including `owner`), which — combined with finding #1 — would matter even more once auth is actually wired in.

**Fix:** Fail startup if `SECRET_KEY` isn't set (or isn't set to the default) in non-debug environments, rather than silently falling back.

**Remediation:** `Settings.__init__` now raises `RuntimeError` at startup if `SECRET_KEY` is empty or equal to the old literal default, unless `DEBUG=true` (in which case a random ephemeral key is generated for local convenience, logged nowhere and not persisted). Verified: `DEBUG=False SECRET_KEY=` refuses to construct `Settings()`; `DEBUG=True SECRET_KEY=` generates a fresh 32-byte key per process. The actual `.env` already had a real random `SECRET_KEY`, so the running stack was unaffected.

---

## 4. Medium — JWT transmitted as a URL query parameter

**Files:** `backend/app/routes/auth.py:87` (`GET /me?token=...`), `frontend/src/api.ts:106` (WebSocket: `?token=${token}&tenant_id=${tenantId}`)

Access tokens in the query string get written to server access logs, proxy logs, and browser history, and can leak via the `Referer` header. Prefer the `Authorization` header (already used elsewhere) for `/me`, and a subprotocol/first-message auth handshake for the WebSocket instead of embedding the token in the URL.

**Remediation:** `/auth/me` now uses `Depends(get_current_user)` and reads identity from `request.state` — no `token` query param at all (this also fixes finding #7, see below). The logs WebSocket (`WS /api/v1/logs/ws/{job_id}`) no longer takes `?token=...&tenant_id=...` in the URL; the client now sends `{"token": "..."}` as its first text frame after the socket opens, and the server (`logs.py`) withholds any log data until it receives and verifies that frame (10s timeout, then closes with code 4401). `frontend/src/api.ts::connectWebSocket` was updated to match. Verified with a raw WebSocket client: no auth message → times out with nothing sent; garbage token → closed with code 4401 "Invalid or expired token"; valid token → streams real `imapsync` log lines.

---

## 5. Low — Permissive CORS

**File:** `backend/app/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

`allow_origins=["*"]` combined with `allow_credentials=True` is a red flag in general (browsers actually reject this combination for credentialed requests, so it's not directly exploitable today since auth here is a header/bearer token rather than cookies) but it's worth tightening to an explicit origin allowlist before this ships, especially once finding #1 is fixed and the API becomes the actual security boundary.

**Remediation:** `main.py` now sets `allow_origins=settings.CORS_ORIGINS`, a comma-separated allowlist read from the new `CORS_ORIGINS` env var (default `http://localhost:3000,http://localhost:4301`, covering both the local Vite dev server and the docker-compose frontend port). `docker-compose.yml`'s `backend` service now passes `CORS_ORIGINS` (and `DEBUG`) through from `.env`. Verified against the live stack: a preflight `OPTIONS` from `http://localhost:4301` (the real frontend origin) gets `200`; one from `http://evil.example` gets `400` (Starlette's CORS middleware rejects disallowed origins this way). Note: the container needed recreating (`docker compose up -d backend`) since env vars aren't picked up by the bind-mount hot-reload.

---

## 6. Low (code quality) — Dead authorization code

**File:** `backend/app/deps/roles.py`

`require_role()` is fully implemented (JWT validation, role check) but unused — see finding #1. Either wire it in or remove it; leaving it unreferenced makes the codebase look more secure than it is on a quick read.

**Remediation:** Rewrote `app/deps/roles.py`: extracted the shared logic into `get_current_user` (now used everywhere auth is required, see #1), and fixed `require_role` itself, which had a second latent bug — it was declared `async def require_role(allowed_roles)`, so calling it as a dependency factory (`Depends(require_role([...]))`) would have handed FastAPI a coroutine object instead of the actual dependency callable. It's now a plain function returning an inner `async def check_role`, so it's usable wherever role-gating (not just authentication) is needed in the future.

---

## 7. Low (bug) — `/auth/me` contract mismatch

**Files:** `backend/app/routes/auth.py:86-87`, `frontend/src/api.ts:67`

Backend:
```python
@router.get("/me", response_model=UserResponse)
async def get_current_user(token: str):   # plain query param, no Depends
```
Frontend:
```ts
getCurrentUser: () => api.get('/auth/me'),   // no token param sent, only the Authorization header
```
`token` is a required query parameter with no default, but the frontend never sends it (it only sets the `Authorization` header via the axios interceptor). Every call to `getCurrentUser()` will 422. Not a security issue, but worth fixing alongside #1/#4 — the natural fix is to make `/me` use the same auth dependency as the rest of the API instead of a bespoke `token` query param.

**Remediation:** Fixed as part of #4 — `/me` (renamed from the shadowing `get_current_user` to `me`) now takes `Depends(get_current_user)` and reads `request.state.user_id`/`request.state.tenant_id`, matching how the frontend already calls it (`api.get('/auth/me')`, relying on the Authorization header interceptor). Verified: `curl -H "Authorization: Bearer <token>" .../auth/me` returns `200` with the correct user.

---

## What's done well

- **SQL injection:** every database query in `db.py`, `job_repo.py`, `auth.py`, `domains.py`, and `logger.py` uses parameterized `?` placeholders — no string-built SQL anywhere, including the schema-migration `ALTER TABLE` statements (column names come from a fixed internal dict, not user input).
- **Password storage:** `AuthService` uses `passlib` bcrypt for hashing/verification, not a home-grown scheme.
- **Command execution:** `ImapsyncWrapper._build_cmd` builds an argv list and calls `subprocess.run`/`Popen` without `shell=True`, so user-supplied emails/passwords/hostnames can't break out into shell metacharacter injection.
- **Tenant scoping at the data layer:** every repository method takes and filters by `tenant_id`, so once authentication is actually enforced upstream (finding #1), the isolation model underneath is sound.

## Suggested priority order (completed, in this order)

1. Fix #1 (wire real auth into jobs/domains/logs routers) — this is the load-bearing fix; several other findings become far less scary once it's in place.
2. Fix #3 (fail closed on missing `SECRET_KEY`) — cheap and removes a full auth-bypass path.
3. Fix #2 (constrain/validate `mailcow_url`) — removes the SSRF primitive.
4. Address #4, #5, #6, #7 as routine cleanup.

## Files touched by the fixes

- `backend/app/deps/roles.py` — rewritten: `get_current_user` + fixed `require_role`
- `backend/app/middleware/tenant.py` — deleted (insecure, superseded by JWT-derived tenant scoping)
- `backend/app/main.py` — drop `TenantMiddleware`, CORS origins from config
- `backend/app/config.py` — fail-closed `SECRET_KEY`, `CORS_ORIGINS` setting
- `backend/app/core/security.py` — new: `validate_public_url` (SSRF guard)
- `backend/app/routes/jobs.py` — router-level auth, `mailcow_url` validation
- `backend/app/routes/domains.py` — router-level auth
- `backend/app/routes/logs.py` — auth on HTTP route, WebSocket first-message handshake
- `backend/app/routes/auth.py` — `/me` uses the standard auth dependency
- `backend/app/auth.py` — JWT `sub` claim stored/read as a string
- `frontend/src/api.ts` — WebSocket sends the token as a first message instead of a URL query param
- `docker-compose.yml`, `.env`, `.env.example` — pass through `CORS_ORIGINS`/`DEBUG`, add a real CORS allowlist default
