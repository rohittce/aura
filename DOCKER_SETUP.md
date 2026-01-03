# Docker Setup Guide

## Quick Start

### Using Docker Compose (Recommended)

```bash
# Start all services (app, database, redis)
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### Using Docker Only

```bash
# Build image
docker build -t aura-music-app .

# Run container
docker run -d \
  --name aura-app \
  -p 8000:10000 \
  -e DATABASE_URL=postgresql://user:pass@host:port/db \
  -e ALLOWED_ORIGINS=http://localhost:8000 \
  -v $(pwd)/data:/app/data \
  aura-music-app
```

## Environment Variables

### Required
- `DATABASE_URL` - PostgreSQL connection string
- `ALLOWED_ORIGINS` - Comma-separated list of allowed CORS origins

### Optional
- `PORT` - Server port (default: 10000)
- `DATA_DIR` - Directory for SQLite data (default: /app/data)
- `REDIS_URL` - Redis connection string (for multi-server Socket.IO)
- `USE_ONLINE_LLM` - Use online LLM APIs (default: true)
- `LLM_API_PROVIDER` - LLM provider (huggingface, replicate, openai)
- `HUGGINGFACE_API_KEY` - Hugging Face API key
- `YOUTUBE_API_KEY` - YouTube Data API key
- `GEMINI_API_KEY` - Google Gemini API key

## Docker Compose Services

### App Service
- **Port**: 8000 (mapped to container port 10000)
- **Volumes**: 
  - `./data:/app/data` - SQLite database (if used)
  - `./static:/app/static` - Static files
- **Dependencies**: db, redis

### Database Service (PostgreSQL)
- **Port**: 5432
- **Database**: aura_music
- **User**: postgres
- **Password**: postgres (change in production!)
- **Volume**: postgres_data (persistent)

### Redis Service (Optional)
- **Port**: 6379
- **Volume**: redis_data (persistent)
- **Purpose**: Socket.IO adapter for multi-server deployments

## Production Deployment

### 1. Update Environment Variables

Edit `docker-compose.yml`:
```yaml
environment:
  - DATABASE_URL=postgresql://user:secure_password@db:5432/aura_music
  - ALLOWED_ORIGINS=https://your-domain.com
  - REDIS_URL=redis://redis:6379
```

### 2. Use Production Database

For production, use an external managed PostgreSQL database:
```yaml
environment:
  - DATABASE_URL=postgresql://user:pass@your-db-host:5432/aura_music
```

Remove the `db` service from docker-compose.yml and update `depends_on`.

### 3. Security

- Change default PostgreSQL password
- Use secrets management (Docker secrets, environment files)
- Enable SSL/TLS for database connections
- Configure firewall rules
- Use reverse proxy (Nginx) for HTTPS

### 4. Scaling

For horizontal scaling with Socket.IO:
1. Use Redis adapter (included in docker-compose.yml)
2. Use load balancer with sticky sessions
3. Configure Redis in WebSocket service

## WebSocket Support

The Dockerfile automatically includes Socket.IO support. The app uses `socketio_asgi` which wraps the FastAPI app with Socket.IO.

**Important**: Ensure your reverse proxy (Nginx, etc.) supports WebSocket upgrades:
```nginx
location /socket.io/ {
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_pass http://app:10000;
}
```

## Database Initialization

Tables are automatically created on first startup. To manually initialize:

```bash
docker-compose exec app python setup_database.py
```

## Troubleshooting

### WebSocket Connection Issues
- Check firewall rules
- Verify reverse proxy WebSocket configuration
- Check CORS settings
- Verify JWT token is valid

### Database Connection Issues
- Check DATABASE_URL format
- Verify database is running: `docker-compose ps db`
- Check logs: `docker-compose logs db`

### Port Conflicts
- Change port mapping in docker-compose.yml
- Check if port is already in use: `netstat -an | grep 8000`

## Development

### Rebuild After Changes
```bash
docker-compose build --no-cache
docker-compose up -d
```

### Access Container Shell
```bash
docker-compose exec app bash
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f app
```

## Health Check

The app includes a health check endpoint:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{"status": "healthy"}
```

## Volume Persistence

Data is persisted in Docker volumes:
- `postgres_data` - PostgreSQL data
- `redis_data` - Redis data
- `./data` - SQLite data (if used)

To backup:
```bash
docker-compose exec db pg_dump -U postgres aura_music > backup.sql
```

