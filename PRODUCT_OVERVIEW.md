# Product Overview: Flask Advanced Admin Platform

## What This Application Is

This is an **internal admin/operations platform** built with Flask (Python) and React. It provides a centralized dashboard for managing users, file uploads, and background jobs within an organization.

---

## Core Features

### 1. User Management
- **User registration and authentication** (JWT-based)
- **Role-based access control** (user vs admin roles)
- Admin-only endpoints for viewing all users

### 2. File Upload Tracking
- Track file uploads across the organization
- Associate uploads with specific users
- Audit trail with timestamps

### 3. Background Job Management
- Monitor async/background job status
- Track job ownership (which user triggered it)
- View job history and status

### 4. Admin Dashboard (React UI)
- Modern dark-themed cyber UI
- Protected routes requiring authentication
- Pages: Dashboard, Users, Uploads, Jobs

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React Admin   │────▶│   Flask API     │────▶│   PostgreSQL    │
│   UI (:3001)    │     │   (:9000)       │     │   (:5432)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌─────────────────┐
                        │  Redis + RQ     │
                        │  (Background    │
                        │   Jobs)         │
                        └─────────────────┘
```

---

## Use Cases & Organizational Value

### Who Uses This?

| Role | Use Case |
|------|----------|
| **System Admins** | Manage user accounts, monitor system health |
| **Operations Team** | Track file uploads, monitor job queues |
| **Developers** | Debug issues, check job status |
| **Compliance/Audit** | Review user activity, upload history |

### Business Problems Solved

1. **Centralized User Management**
   - Single source of truth for user accounts
   - Role-based permissions prevent unauthorized access
   - Audit trail for compliance

2. **Operational Visibility**
   - Real-time view of background job status
   - Track file processing pipelines
   - Identify bottlenecks and failures

3. **Security & Compliance**
   - JWT-based authentication
   - Admin-only access to sensitive data
   - Logging with request correlation (X-Request-ID)

4. **Developer Productivity**
   - Self-service dashboard reduces support tickets
   - Quick debugging without database access
   - Health endpoints for monitoring

---

## What Organizations Achieve

| Benefit | Description |
|---------|-------------|
| **Reduced Operational Overhead** | Self-service admin reduces IT support burden |
| **Faster Incident Response** | Real-time visibility into jobs and uploads |
| **Improved Security Posture** | Centralized auth, role-based access, audit logs |
| **Compliance Readiness** | User activity tracking, upload audit trail |
| **Scalability** | Containerized architecture scales with demand |

---

## Typical Deployment Scenarios

### 1. Internal Tools Platform
- Run alongside other internal services
- SSO integration possible via JWT
- Used by ops/admin teams

### 2. SaaS Backend Admin
- Admin panel for a customer-facing SaaS product
- Manage customer accounts and data
- Monitor background processing

### 3. Data Pipeline Dashboard
- Track ETL job execution
- Monitor file ingestion
- Alert on failures

---

## Extension Points

This platform is designed to be extended:

| Feature | How to Add |
|---------|------------|
| **S3 Integration** | boto3 already included; add upload routes |
| **Redis Queues** | redis + rq already included; add job workers |
| **Email Notifications** | Add Flask-Mail for alerts |
| **OAuth/SSO** | Extend auth routes for Google/Okta |
| **API Rate Limiting** | Add Flask-Limiter |
| **Audit Logging** | Extend middleware for detailed logs |

---

## Quick Start for Testing

### 1. Start Services
```bash
docker compose up --build -d
```

### 2. Create Admin User
```bash
# Option A: Via API
curl -X POST http://localhost:9000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123!"}'

docker compose exec db psql -U postgres -d flaskdb \
  -c "UPDATE \"user\" SET role='admin' WHERE email='admin@example.com';"

# Option B: Via seed script
docker compose exec api python scripts/seed_admin.py
```

### 3. Login to UI
- Open: http://localhost:3001/ui/login
- Email: `admin@example.com`
- Password: `Admin123!`

### 4. Explore Dashboard
- `/ui/dashboard` - Overview
- `/ui/users` - User list
- `/ui/uploads` - File uploads
- `/ui/jobs` - Background jobs

### 5. Test API Directly
```bash
# Get token
TOKEN=$(curl -s -X POST http://localhost:9000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123!"}' \
  | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

# Call admin endpoint
curl -s http://localhost:9000/admin/users \
  -H "Authorization: Bearer $TOKEN"
```

---

## Files Reference

| File | Purpose |
|------|---------|
| `TESTING_CHECKLIST.md` | Full testing guide |
| `LOCAL_RUN.md` | Docker commands reference |
| `SECURITY.md` | Security configuration |
| `.env.example` | Environment variables template |
| `scripts/seed_admin.py` | Create admin user |
