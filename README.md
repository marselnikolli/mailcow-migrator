# mailcow Mail Migration SaaS Platform

A complete email migration SaaS platform that enables seamless mail migrations from external sources to mailcow using IMAP synchronization.

## Features

- 🔐 **Multi-tenant SaaS**: Complete tenant isolation with role-based access control
- 📧 **Email Migration**: IMAP-based email migration with IMAPSYNC wrapper
- 📊 **Real-time Monitoring**: Live logs and progress tracking for migration jobs
- 🌐 **RESTful API**: FastAPI backend with JWT authentication
- 💻 **Modern UI**: React/Vite frontend with TailwindCSS
- 🔄 **Queue Management**: Redis-based job queue with retry mechanism
- 📝 **Structured Logging**: Comprehensive job logging with timestamps and levels
- 🐳 **Docker Ready**: Complete Docker Compose setup for easy deployment

## Architecture

### Backend
- **FastAPI**: Modern Python web framework
- **SQLite**: Lightweight database for multi-tenant data
- **Redis**: Job queue and caching
- **IMAPSYNC**: Command-line email synchronization tool

### Frontend
- **React 18**: UI library
- **Vite**: Fast build tool
- **TailwindCSS**: Utility-first CSS framework
- **Axios**: HTTP client with interceptors

## Getting Started

### Prerequisites
- Docker & Docker Compose
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### Installation

1. **Clone and navigate to project**
```bash
cd mailcow-migrator
```

2. **Create .env file**
```bash
cp .env.example .env
# Edit .env with your Mailcow and IMAP settings
```

3. **Start with Docker Compose**
```bash
docker-compose up --build
```

4. **Access the application**
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Local Development

**Backend Setup:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend Setup:**
```bash
cd frontend
npm install
npm run dev
```

## Project Structure

```
mailcow-migrator/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry point
│   │   ├── config.py            # Configuration management
│   │   ├── db.py                # Database initialization
│   │   ├── auth.py              # JWT authentication
│   │   ├── models.py            # Pydantic models
│   │   ├── middleware/
│   │   │   └── tenant.py        # Tenant middleware
│   │   ├── routes/
│   │   │   ├── auth.py          # Auth endpoints
│   │   │   ├── jobs.py          # Job management endpoints
│   │   │   ├── domains.py       # Domain management endpoints
│   │   │   └── logs.py          # Log endpoints with WebSocket
│   │   ├── core/
│   │   │   ├── mailcow.py       # Mailcow API client
│   │   │   ├── domains.py       # Domain service
│   │   │   ├── imapsync.py      # IMAPSYNC wrapper
│   │   │   ├── queue.py         # Redis queue management
│   │   │   ├── worker.py        # Background worker
│   │   │   └── logger.py        # Structured logging
│   │   ├── repositories/
│   │   │   └── job_repo.py      # Job data access
│   │   └── deps/
│   │       └── roles.py         # Role-based dependencies
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx    # Main dashboard
│   │   │   ├── Jobs.tsx         # Job listing and management
│   │   │   ├── Domains.tsx      # Domain management
│   │   │   └── Login.tsx        # Auth page
│   │   ├── components/
│   │   │   └── LiveLogs.tsx     # Real-time log viewer
│   │   ├── api.ts               # API client
│   │   ├── main.tsx             # React entry point
│   │   └── index.css            # TailwindCSS styles
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── docker-compose.yml           # Docker Compose configuration
├── .env.example                 # Environment variables template
└── README.md
```

## API Documentation

### Authentication
- `POST /api/v1/auth/register` - Register new tenant and user
- `POST /api/v1/auth/login` - Login and get JWT token
- `GET /api/v1/auth/me` - Get current user info

### Jobs
- `POST /api/v1/jobs/create` - Create migration job
- `GET /api/v1/jobs/list` - List jobs with filtering
- `GET /api/v1/jobs/{job_id}` - Get job details
- `POST /api/v1/jobs/retry/{job_id}` - Retry failed job

### Domains
- `POST /api/v1/domains/add` - Add domain
- `GET /api/v1/domains/list` - List domains
- `GET /api/v1/domains/validate/{domain}` - Validate domain in Mailcow

### Logs
- `GET /api/v1/logs/{job_id}` - Get job logs
- `WS /api/v1/logs/ws/{job_id}` - WebSocket for real-time logs

## Key Features Explained

### Multi-Tenant Isolation
- All database queries filtered by `tenant_id` (System-wide rule)
- Tenant middleware extracts and validates tenant from `X-Tenant-ID` header
- Role-based access control: owner, admin, operator, viewer

### Job Processing
- Jobs are stored in SQLite with status tracking
- Redis queue holds pending jobs for processing
- Background worker processes jobs with automatic retry (max 3 times)
- IMAPSYNC handles secure IMAP-to-IMAP email synchronization

### Real-time Features
- WebSocket endpoint for live log streaming
- React component with auto-scrolling log viewer
- Job progress tracking and status updates

### Security
- JWT-based authentication with configurable expiry
- Bcrypt password hashing
- Tenant isolation at middleware level
- Role-based endpoint access control

## Environment Variables

See `.env.example` for all available configuration options:

```
# Mailcow Configuration
MAILCOW_URL=http://mailcow:8080
MAILCOW_API_KEY=your_api_key

# Redis Configuration
REDIS_URL=redis://redis:6379

# Security
SECRET_KEY=your_secret_key_change_me
DEBUG=False

# Source IMAP Settings
SOURCE_IMAP_HOST=imap.gmail.com
SOURCE_IMAP_PORT=993
```

## Running the Background Worker

To process migration jobs, start a worker process:

```bash
python -m app.core.worker
```

In production, use a process manager like systemd or supervisord.

## Database Schema

The system uses SQLite with the following tables:
- **tenants**: SaaS tenant organizations
- **users**: User accounts with role assignment
- **domains**: Email domains to migrate to
- **jobs**: Migration jobs with status tracking
- **logs**: Structured job logs
- **api_keys**: API authentication keys

All tables include `tenant_id` for multi-tenant isolation.

## Development Notes

- All endpoints require `X-Tenant-ID` header (except /health, /auth/register, /auth/login)
- All database queries must filter by tenant_id (system-wide requirement)
- Job status flow: pending → running → completed/failed
- Max job retries: 3 attempts before marking as failed
- Log retention: 7 days in Redis

## License

MIT License - See LICENSE file for details

## Support

For issues, feature requests, or contributions, please refer to the repository's issue tracker.
