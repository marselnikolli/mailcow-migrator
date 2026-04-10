# Quick Start Guide

## 30-Second Setup

1. **Copy environment template**
   ```bash
   cp .env.example .env
   ```

2. **Edit .env with your Mailcow credentials**
   ```bash
   nano .env
   # Update MAILCOW_URL and MAILCOW_API_KEY
   ```

3. **Start everything**
   ```bash
   docker-compose up --build
   ```

4. **Open browser**
   - Go to http://localhost:3000
   - Create account (set tenant name and login credentials)
   - Start migrating emails!

## First Migration Steps

1. **Add Domain** → Go to "Domains" tab
   - Example: `example.com`
   - Click "Add Domain"

2. **Create Migration Job** → Go to "Dashboard"
   - Source Email: `john@gmail.com`
   - Source Password: (Gmail app password)
   - Target Email: `john@example.com`
   - Target Password: (New mailcow password)
   - Click "Start Migration"

3. **Monitor Progress**
   - Watch the dashboard stats
   - Click on job row to see live logs
   - Logs stream in real-time from worker

## Configuration

### Minimal Setup (.env)
```bash
MAILCOW_URL=http://mailcow-host:8080
MAILCOW_API_KEY=your_api_key_from_mailcow
SECRET_KEY=any_random_string_change_later
```

### Optional Settings
```bash
SOURCE_IMAP_HOST=imap.gmail.com
SOURCE_IMAP_PORT=993
DEBUG=False
```

## Common Issues

### "Unable to connect to Mailcow"
- Check MAILCOW_URL is accessible from Docker container
- Verify MAILCOW_API_KEY is correct
- Ensure Mailcow API is enabled

### "X-Tenant-ID header is required"
- Frontend should send this automatically
- If using curl: `curl -H "X-Tenant-ID: 1" http://localhost:8000/api/v1/jobs/list`

### Redis connection error
- Ensure Redis container is running: `docker ps | grep redis`
- Check REDIS_URL matches service name

### Database locked error
- SQLite has single-writer limitation
- Already handled in code, but avoid concurrent writes
- Consider PostgreSQL for production

## Useful Commands

```bash
# View logs
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f worker

# Access container shell
docker exec -it mailcow-migrator-backend-1 bash

# Check Redis queue
docker exec mailcow-migrator-redis-1 redis-cli llen mailcow:jobs:queue

# Stop all services
docker-compose down

# Reset database (caution!)
rm mailcow.db && docker-compose restart backend
```

## API Examples

### Register/Login
```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "password123",
    "tenant_name": "My Company"
  }'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "password123",
    "tenant_id": 1
  }'
```

### Create Migration Job
```bash
curl -X POST http://localhost:8000/api/v1/jobs/create \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Tenant-ID: 1" \
  -d '{
    "source_email": "john@gmail.com",
    "source_password": "app_password",
    "target_email": "john@company.com",
    "target_password": "new_password",
    "domain": "company.com"
  }'
```

### Get Job Status
```bash
curl http://localhost:8000/api/v1/jobs/list \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Tenant-ID: 1"
```

## Next Steps

1. **Configure Mailcow**: Ensure your Mailcow instance is accessible and API is enabled
2. **Test Migration**: Create a test user and run a sample migration
3. **Monitor Logs**: Check the live logs during migration
4. **Scale Workers**: Run multiple worker instances for higher throughput
5. **Setup Backup**: Configure automated database backups

## Support

- Check [README.md](README.md) for full documentation
- Review [DEPLOYMENT.md](DEPLOYMENT.md) for production setup
- Check API docs at http://localhost:8000/docs

## Performance Tips

- Use strong passwords to prevent auth issues
- Gmail users need ["App Passwords"](https://support.google.com/accounts/answer/185833)
- Disable anti-virus scanning during large migrations
- Monitor the Redis queue size for bottlenecks
- Run multiple worker instances for parallel processing

Ready to migrate? Start with step 3 above! 🚀
