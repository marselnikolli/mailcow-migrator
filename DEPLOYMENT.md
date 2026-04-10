# Deployment Guide

## Local Development

1. **Start services with Docker Compose**
```bash
docker-compose up --build
```

2. **Access the application**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - OpenAPI Docs: http://localhost:8000/docs

## Production Deployment

### Prerequisites
- Docker & Docker Compose
- SSL/TLS certificates (for HTTPS)
- Mailcow instance with API access
- Domain with DNS configured

### Steps

1. **Clone the repository**
```bash
git clone <repo-url>
cd mailcow-migrator
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your production values
```

3. **Build and start with production compose file**
```bash
docker-compose -f docker-compose.prod.yml up -d
```

### Configuration

**Important environment variables:**

```bash
# Change these in production
SECRET_KEY=<generate-secure-key>
MAILCOW_API_KEY=<your-mailcow-api-key>
MAILCOW_URL=<your-mailcow-url>
DEBUG=False
```

Generate a secure SECRET_KEY:
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Scaling

**Run multiple workers:**

Update `docker-compose.prod.yml`:
```yaml
worker:
  deploy:
    replicas: 3
```

### Monitoring

Monitor container health:
```bash
docker-compose logs -f backend
docker-compose logs -f worker
docker-compose logs -f frontend
```

Check Redis queue size:
```bash
docker exec mailcow-migrator-redis-1 redis-cli llen mailcow:jobs:queue
```

### Backup

Backup important data:

1. **Database backup**
```bash
docker exec mailcow-migrator-backend-1 cp mailcow.db /backup/mailcow.db.backup
```

2. **Redis persistence** is enabled in docker-compose.prod.yml

### SSL/TLS Setup

For production, use Nginx reverse proxy with Let's Encrypt:

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Systemd Service (Alternative to Docker)

Create `/etc/systemd/system/mailcow-migrator.service`:

```ini
[Unit]
Description=mailcow Mail Migrator
After=network.target redis.service

[Service]
Type=notify
User=www-data
WorkingDirectory=/opt/mailcow-migrator

Environment="PATH=/opt/mailcow-migrator/venv/bin"
EnvironmentFile=/opt/mailcow-migrator/.env

ExecStart=/opt/mailcow-migrator/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable mailcow-migrator
sudo systemctl start mailcow-migrator
```

## Troubleshooting

### Database locked error
```bash
# SQLite needs to be used with single writer
# This is configured in db.py
```

### WebSocket connection issues
Ensure your proxy forwards WebSocket headers:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Memory issues
Monitor container memory:
```bash
docker stats
```

Adjust limits in compose file:
```yaml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
```

## Health Checks

API health endpoint:
```bash
curl http://localhost:8000/health
```

Redis connectivity:
```bash
docker exec mailcow-migrator-redis-1 redis-cli ping
```

Database connectivity:
```bash
docker exec mailcow-migrator-backend-1 python -c "from app.db import get_db; get_db()"
```

## Performance Tips

1. **Use Redis for caching** - Already implemented
2. **Enable database WAL mode** - Improve SQLite performance
3. **Run multiple worker instances** - Process jobs faster
4. **Monitor queue size** - Add alerts when queue grows
5. **Log rotation** - Configure Docker log drivers

## Security Hardening

1. **Change default SECRET_KEY**
2. **Use strong MAILCOW_API_KEY**
3. **Enable HTTPS/SSL**
4. **Restrict network access** - Use firewall rules
5. **Regular backups** - Automated daily backups
6. **Keep dependencies updated** - Regular security patches

## Rollback

To rollback to previous version:

```bash
# Stop current version
docker-compose down

# Restore database backup
cp /backup/mailcow.db.backup ./mailcow.db

# Checkout previous code version
git checkout <previous-version>

# Restart
docker-compose -f docker-compose.prod.yml up -d
```
