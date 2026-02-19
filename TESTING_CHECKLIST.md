# Testing Checklist

## Prerequisites

```bash
# Ensure Docker is running
docker info

# Start all services
docker compose up --build -d

# Wait for services to be ready
docker compose ps  # All should show "Up" and db should be "healthy"
```

---

## 0. Create Test Admin User

### Option A: Via API + SQL
```bash
# Register user
curl -X POST http://localhost:9000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123!"}'

# Promote to admin
docker compose exec db psql -U postgres -d flaskdb \
  -c "UPDATE \"user\" SET role='admin' WHERE email='admin@example.com';"
```

### Option B: Via Seed Script
```bash
docker compose exec api python scripts/seed_admin.py
```

### Option C: Custom Credentials
```bash
ADMIN_EMAIL=myemail@example.com ADMIN_PASSWORD=MySecurePass123 \
  docker compose exec api python scripts/seed_admin.py
```

### Default Test Credentials
| Field | Value |
|-------|-------|
| Email | `admin@example.com` |
| Password | `Admin123!` |
| Role | `admin` |
| UI Login | http://localhost:3001/ui/login |

---

## 1. Smoke Tests

### 1.1 Services Running
```bash
docker compose ps
```
**Expected:** All 3 containers running (db healthy, api up, ui up)

### 1.2 Health Check
```bash
curl -s http://localhost:9000/healthz
```
**Expected:** `{"status":"ok"}`

### 1.3 Home Page
```bash
curl -s http://localhost:9000/ | head -5
```
**Expected:** HTML with "Advanced Flask Application"

### 1.4 API Logs (no errors)
```bash
docker compose logs api --tail 20
```
**Expected:** 
- `>>> Postgres is ready!`
- `>>> Running Alembic migrations...`
- `>>> Starting Gunicorn...`
- No ERROR lines

---

## 2. Database Tests

### 2.1 DB Container Healthy
```bash
docker compose ps db
```
**Expected:** Status shows `(healthy)`

### 2.2 Tables Exist
```bash
docker compose exec db psql -U postgres -d flaskdb -c "\dt"
```
**Expected:** Tables: `alembic_version`, `user`, `file_upload`, `job`

### 2.3 Alembic Version
```bash
docker compose exec db psql -U postgres -d flaskdb -c "SELECT * FROM alembic_version;"
```
**Expected:** `05305ac13612` (or latest migration)

### 2.4 Manual DB Connection
```bash
# From host
psql -h localhost -p 5432 -U postgres -d flaskdb
# Password: password

# From API container
docker compose exec api psql -h db -U postgres -d flaskdb
```

---

## 3. API Tests

### 3.1 Public Endpoints

```bash
# Health check
curl -s http://localhost:9000/healthz
# Expected: {"status":"ok"}

# Home page
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/
# Expected: 200
```

### 3.2 Auth Flow

```bash
# Register new user
curl -s -X POST http://localhost:9000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'
# Expected: {"message":"User created"} or {"error":"Email already exists"}

# Login
curl -s -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}'
# Expected: {"access_token":"eyJ..."}

# Get current user (protected)
TOKEN=$(curl -s -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

curl -s http://localhost:9000/auth/me -H "Authorization: Bearer $TOKEN"
# Expected: {"email":"test@example.com","id":1}
```

### 3.3 Admin Endpoints (require admin role)

```bash
# Promote user to admin first
docker compose exec db psql -U postgres -d flaskdb \
  -c "UPDATE \"user\" SET role='admin' WHERE email='test@example.com';"

# Get fresh token and test admin endpoints
TOKEN=$(curl -s -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpass123"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

curl -s http://localhost:9000/admin/users -H "Authorization: Bearer $TOKEN"
# Expected: [{"id":1,"email":"test@example.com","role":"admin",...}]

curl -s http://localhost:9000/admin/uploads -H "Authorization: Bearer $TOKEN"
# Expected: [] (empty array if no uploads)

curl -s http://localhost:9000/admin/jobs -H "Authorization: Bearer $TOKEN"
# Expected: [] (empty array if no jobs)
```

---

## 4. UI Tests

### 4.1 UI Loads
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:3001/
# Expected: 200
```

### 4.2 Browser Tests
Open http://localhost:3001 in browser:

| Page | URL | Expected |
|------|-----|----------|
| Login | http://localhost:3001/ui/login | Login form visible |
| Dashboard | http://localhost:3001/ui/dashboard | Redirects to login if not authenticated |
| Users | http://localhost:3001/ui/users | Admin user list (after login) |
| Uploads | http://localhost:3001/ui/uploads | Upload list |
| Jobs | http://localhost:3001/ui/jobs | Job list |

### 4.3 Login Flow
1. Go to http://localhost:3001/ui/login
2. Enter: `test@example.com` / `testpass123`
3. Click Login
4. Should redirect to Dashboard

### 4.4 CORS Check
```bash
curl -sI -X OPTIONS http://localhost:9000/auth/login \
  -H "Origin: http://localhost:3001" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control
# Expected: Access-Control-Allow-Origin: http://localhost:3001
```

---

## 5. Troubleshooting

### Container Won't Start
```bash
docker compose logs api
docker compose logs db
```
Look for: connection errors, missing env vars, migration failures

### Database Connection Failed
```bash
# Check db is healthy
docker compose ps

# Test connection from API
docker compose exec api pg_isready -h db -U postgres

# Check env vars
docker compose exec api env | grep -E "SQLALCHEMY|POSTGRES"
```

### Migrations Failed
```bash
# Check current version
docker compose exec db psql -U postgres -d flaskdb -c "SELECT * FROM alembic_version;"

# Re-run migrations
docker compose exec api flask db upgrade

# Check for migration errors
docker compose logs api | grep -i "alembic\|migration"
```

### API Returns 500
```bash
# Check logs for stack trace
docker compose logs api --tail 50

# Common causes:
# - Missing env vars
# - Database not ready
# - Import errors
```

### UI Blank Screen
```bash
# Check UI logs
docker compose logs ui --tail 20

# Check if bundle loads
curl -sI http://localhost:3001/static/js/main.*.js

# Common causes:
# - Build failed (check logs)
# - Route not matched (check App.jsx)
```

### CORS Errors in Browser
```bash
# Verify CORS headers
curl -sI http://localhost:9000/auth/login \
  -H "Origin: http://localhost:3001" | grep -i access-control

# If missing, check app/__init__.py for CORS config
```

---

## 6. Full Reset

```bash
# Stop and remove everything
docker compose down -v

# Rebuild from scratch
docker compose build --no-cache

# Start fresh
docker compose up -d

# Verify
docker compose ps
curl -s http://localhost:9000/healthz
```

---

## 7. LocalStack / S3 Tests

### 7.1 LocalStack Running
```bash
docker compose ps localstack
# Expected: Status shows "healthy"
```

### 7.2 Bucket Created
```bash
# Check bucket exists
aws --endpoint-url=http://localhost:4566 s3 ls
# Expected: controlhub-uploads

# Or using curl
curl -s http://localhost:4566/_localstack/health
# Expected: {"services":{"s3":"running"}}
```

### 7.3 Test Upload (manual)
```bash
# Upload a test file
echo "test content" > /tmp/test.txt
aws --endpoint-url=http://localhost:4566 s3 cp /tmp/test.txt s3://controlhub-uploads/test.txt

# Verify upload
aws --endpoint-url=http://localhost:4566 s3 ls s3://controlhub-uploads/
# Expected: test.txt listed
```

### 7.4 AWS CLI Setup (for local testing)
```bash
# If you don't have AWS CLI, install it or use docker:
docker run --rm -it --network host amazon/aws-cli \
  --endpoint-url=http://localhost:4566 s3 ls

# Configure credentials for LocalStack (any values work)
aws configure
# AWS Access Key ID: test
# AWS Secret Access Key: test
# Default region: us-east-1
# Default output: json
```

---

## 8. Enterprise Module Tests

### 8.1 Feature Flags Check
```bash
curl -s http://localhost:9000/features
# Expected: {"service_accounts":true,"notifications":true,"integrations":true,"assets":true}
```

### 8.2 Service Accounts API
```bash
# Create service account
curl -s -X POST http://localhost:9000/admin/service-accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"CI/CD Bot","description":"For deployments"}'
# Expected: {"message":"Service account created","service_account":{...}}

# Create API key
SA_ID=1  # Use ID from previous response
curl -s -X POST http://localhost:9000/admin/service-accounts/$SA_ID/keys \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"deploy-key","scopes":["uploads.read","jobs.read"]}'
# Expected: {"key":"ch_...","api_key":{...}}
```

### 8.3 Notifications API
```bash
# Create notification channel
curl -s -X POST http://localhost:9000/admin/notification-channels \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"webhook","name":"Test Webhook","config":{"url":"https://httpbin.org/post"}}'
# Expected: {"message":"Notification channel created",...}

# Create alert rule
curl -s -X POST http://localhost:9000/admin/alert-rules \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Job Failures","event_type":"job.failed","severity":"high","channel_ids":[1]}'
# Expected: {"message":"Alert rule created",...}
```

### 8.4 Integrations API
```bash
# Create webhook integration
curl -s -X POST http://localhost:9000/admin/integrations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"webhook","name":"SIEM Feed","config":{"url":"https://httpbin.org/post"}}'
# Expected: {"message":"Integration created",...}

# Quick audit export
curl -s -X POST http://localhost:9000/admin/audit-exports/now \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"format":"csv"}' -o audit_export.csv
# Expected: CSV file downloaded
```

### 8.5 Assets API
```bash
# Create asset
curl -s -X POST http://localhost:9000/admin/assets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Dev Laptop","type":"laptop","location":"Office A","department":"Engineering"}'
# Expected: {"message":"Asset created","asset":{"asset_tag":"LPT-0001",...}}

# List assets
curl -s http://localhost:9000/admin/assets \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"items":[...],"total":1,...}

# Get asset stats
curl -s http://localhost:9000/admin/assets/stats \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"total":1,"by_type":{"laptop":1},...}
```

### 8.6 UI Tests for Enterprise Features

| Page | URL | Test |
|------|-----|------|
| Service Accounts | `/ui/service-accounts` | Create account, generate key |
| Notifications | `/ui/notifications` | Create channel, test delivery |
| Alert Rules | `/ui/alert-rules` | Create rule, view history |
| Integrations | `/ui/integrations` | Create webhook, view logs |
| Audit Export | `/ui/audit-export` | Quick export, create job |
| Assets | `/ui/assets` | Create asset, view detail |

---

## Service Endpoints Summary

| Service | URL | Purpose |
|---------|-----|---------|
| API | http://localhost:9000 | Flask backend |
| Health | http://localhost:9000/healthz | Health check |
| Features | http://localhost:9000/features | Feature flags |
| Admin UI | http://localhost:3001 | React frontend |
| Postgres | localhost:5432 | Database |
| LocalStack | http://localhost:4566 | S3-compatible storage |
| LocalStack Health | http://localhost:4566/_localstack/health | LocalStack status |

---

## API Endpoints Reference

### Core Endpoints
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/healthz` | Health check |
| GET | `/features` | Feature flags |
| POST | `/auth/register` | Register user |
| POST | `/auth/login` | Login |
| GET | `/auth/me` | Current user |

### Admin Endpoints (require admin role)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/admin/users` | List users |
| GET | `/admin/uploads` | List uploads |
| GET | `/admin/jobs` | List jobs |
| GET | `/admin/audit-logs` | List audit logs |

### Enterprise Endpoints (feature-flagged)
| Method | Endpoint | Feature Flag |
|--------|----------|--------------|
| GET/POST | `/admin/service-accounts` | FEATURE_SERVICE_ACCOUNTS |
| GET/POST | `/admin/notification-channels` | FEATURE_NOTIFICATIONS |
| GET/POST | `/admin/alert-rules` | FEATURE_NOTIFICATIONS |
| GET | `/admin/alerts` | FEATURE_NOTIFICATIONS |
| GET/POST | `/admin/integrations` | FEATURE_INTEGRATIONS |
| GET/POST | `/admin/audit-exports` | FEATURE_INTEGRATIONS |
| GET/POST | `/admin/assets` | FEATURE_ASSETS |
