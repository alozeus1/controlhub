# Local Development with Docker Compose

## Prerequisites
- Docker Desktop installed and running
- Copy `.env.example` to `.env` and adjust values if needed

## Quick Start

### Start all services
```bash
docker compose up --build
```

### Start in detached mode (background)
```bash
docker compose up --build -d
```

### Stop all services
```bash
docker compose down
```

### Stop and remove volumes (reset database)
```bash
docker compose down -v
```

### Rebuild without cache
```bash
docker compose build --no-cache
docker compose up
```

## Service Endpoints

| Service | URL |
|---------|-----|
| API | http://localhost:9000 |
| Health Check | http://localhost:9000/healthz |
| Admin UI | http://localhost:3001 |
| Postgres | localhost:5432 |

## Verify Health

```bash
curl http://localhost:9000/healthz
# Expected: {"status":"ok"}
```

## View Logs

### All services
```bash
docker compose logs -f
```

### API only
```bash
docker compose logs -f api
```

### Database only
```bash
docker compose logs -f db
```

## Run Migrations Manually

```bash
docker compose exec api flask db upgrade
```

### Create a new migration
```bash
docker compose exec api flask db migrate -m "description of change"
```

## Connect to Postgres

### From host machine
```bash
psql -h localhost -p 5432 -U postgres -d flaskdb
# Password: password (or as set in .env)
```

### From inside the API container
```bash
docker compose exec api psql -h db -U postgres -d flaskdb
```

### From a separate psql container
```bash
docker compose exec db psql -U postgres -d flaskdb
```

## JWT Configuration

JWT settings are configured via environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | (required in prod) | Secret key for signing tokens |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | Token expiry in seconds (1 hour) |
| `JWT_TOKEN_LOCATION` | `headers` | Where to look for tokens |
| `JWT_HEADER_NAME` | `Authorization` | Header name for token |
| `JWT_HEADER_TYPE` | `Bearer` | Token prefix in header |

### Example authenticated request
```bash
# Get a token (adjust endpoint as needed)
TOKEN=$(curl -s -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"secret"}' | jq -r '.access_token')

# Use the token
curl -H "Authorization: Bearer $TOKEN" http://localhost:9000/admin/users
```

## Troubleshooting

### Container won't start
```bash
# Check logs for errors
docker compose logs api

# Rebuild from scratch
docker compose down -v
docker compose build --no-cache
docker compose up
```

### Database connection issues
```bash
# Verify db container is healthy
docker compose ps

# Test connection from API container
docker compose exec api pg_isready -h db -U postgres
```

### Reset everything
```bash
docker compose down -v --rmi local
docker compose up --build
```
