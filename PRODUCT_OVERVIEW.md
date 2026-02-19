# Web Forx ControlHub

**Admin, audit, and operational control for modern teams.**

*by Web Forx Global Inc.*

## What This Application Is

Web Forx ControlHub is an **enterprise admin/operations platform** built with Flask (Python) and React. It provides a centralized dashboard for managing users, file uploads, background jobs, governance workflows, and IT assets within an organization.

---

## Core Features

### 1. User Management
- **User registration and authentication** (JWT-based)
- **Role-based access control** (viewer, user, admin, superadmin)
- Admin-only endpoints for viewing all users

### 2. File Upload Tracking
- Track file uploads across the organization (S3-compatible storage)
- Associate uploads with specific users
- Audit trail with timestamps

### 3. Background Job Management
- Monitor async/background job status
- Track job ownership (which user triggered it)
- View job history and status

### 4. Governance & Approvals
- Define policies for protected actions
- Multi-level approval workflows
- Policy enforcement with audit trail

### 5. ControlHub Dashboard (React UI)
- Modern dark-themed enterprise UI
- Protected routes requiring authentication
- Dynamic navigation based on enabled features
- Pages: Dashboard, Users, Uploads, Jobs, Audit Logs, Governance, and Enterprise modules

---

## Enterprise Modules (Feature-Flagged)

ControlHub includes four enterprise modules that can be independently enabled:

### Module A: Service Accounts & API Keys
- Create service accounts for programmatic access
- Generate and manage API keys with scopes
- Key expiration and revocation
- API key authentication middleware

### Module B: Notifications & Alerting
- Configure notification channels (Email, Slack, Webhook)
- Create alert rules based on system events
- Event-driven notifications with delivery tracking
- Support for 15+ event types

### Module C: Integrations & Audit Export
- Webhook integrations with HMAC signing
- SIEM integration (CEF format)
- Audit log export (CSV, JSON, JSONL)
- Delivery logging and failure tracking

### Module D: Asset Inventory (Light CMDB)
- IT asset tracking with auto-generated tags
- Full lifecycle management (active → retired)
- Change history with full audit trail
- Warranty expiration tracking
- Custom attributes and tagging

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ControlHub    │────▶│   Flask API     │────▶│   PostgreSQL    │
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
| **System Admins** | Manage user accounts, service accounts, IT assets |
| **Operations Team** | Track uploads, monitor jobs, manage alerts |
| **Security Team** | Configure integrations, export audit logs, monitor events |
| **IT Asset Managers** | Track hardware/software inventory, warranty management |
| **Developers** | Debug issues, use API keys for automation |
| **Compliance/Audit** | Review activity, export reports, policy enforcement |

### Business Problems Solved

1. **Centralized User Management**
   - Single source of truth for user accounts
   - Role-based permissions prevent unauthorized access
   - Service accounts for programmatic access
   - Audit trail for compliance

2. **Operational Visibility**
   - Real-time view of background job status
   - Track file processing pipelines
   - Identify bottlenecks and failures
   - Alert on critical events

3. **Security & Compliance**
   - JWT-based authentication + API key auth
   - Admin-only access to sensitive data
   - Logging with request correlation (X-Request-ID)
   - Audit log export for compliance reporting

4. **Developer Productivity**
   - Self-service dashboard reduces support tickets
   - Quick debugging without database access
   - API keys for CI/CD integration
   - Health endpoints for monitoring

5. **IT Asset Management**
   - Track hardware and software inventory
   - Warranty and lifecycle management
   - Department and location tracking
   - Full change history

---

## What Organizations Achieve

| Benefit | Description |
|---------|-------------|
| **Reduced Operational Overhead** | Self-service admin reduces IT support burden |
| **Faster Incident Response** | Real-time alerts and visibility into system events |
| **Improved Security Posture** | Centralized auth, API key management, audit logs |
| **Compliance Readiness** | Full audit trail, exportable reports, policy enforcement |
| **IT Asset Visibility** | Complete inventory tracking with change history |
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

## Feature Flags

Enterprise modules can be enabled/disabled via environment variables:

| Flag | Default | Description |
|------|---------|-------------|
| `FEATURE_SERVICE_ACCOUNTS` | `true` | Service accounts & API keys |
| `FEATURE_NOTIFICATIONS` | `true` | Notification channels & alert rules |
| `FEATURE_INTEGRATIONS` | `true` | Webhooks & audit export |
| `FEATURE_ASSETS` | `true` | IT asset inventory |

Example to disable a feature:
```bash
FEATURE_ASSETS=false docker compose up -d
```

---

## Extension Points

This platform is designed to be extended:

| Feature | Status |
|---------|--------|
| **S3 Integration** | ✅ Implemented (LocalStack for dev) |
| **Audit Logging** | ✅ Implemented with export |
| **Notifications** | ✅ Email, Slack, Webhook channels |
| **API Keys** | ✅ Scoped API key authentication |
| **Webhooks** | ✅ HMAC-signed webhook delivery |
| **SIEM Export** | ✅ CEF format for SIEM systems |
| **OAuth/SSO** | Ready to extend auth routes |
| **API Rate Limiting** | Add Flask-Limiter |

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

Based on the TESTING_CHECKLIST.md file I read earlier, the default
   admin user credentials are:

   Field        │ Value
   -------------+--------------------
   **Email**    │ `admin@example.com`
   **Password** │ `Admin123!`

   You can create this admin user by running:

   bash
     docker compose exec api python scripts/seed_admin.py

   Or with custom credentials:

   bash
     ADMIN_EMAIL=myemail@example.com ADMIN_PASSWORD=MySecurePass123 \
       docker compose exec api python scripts/seed_admin.py

### 4. Explore Dashboard
- `/ui/dashboard` - Overview
- `/ui/users` - User list
- `/ui/uploads` - File uploads
- `/ui/jobs` - Background jobs
- `/ui/audit-logs` - Audit trail
- `/ui/policies` - Governance policies
- `/ui/approvals` - Approval workflows

### 5. Explore Enterprise Features
- `/ui/service-accounts` - Service accounts & API keys
- `/ui/notifications` - Notification channels
- `/ui/alert-rules` - Alert rule configuration
- `/ui/integrations` - Webhook integrations
- `/ui/audit-export` - Export audit logs
- `/ui/assets` - IT asset inventory

### 6. Test API Directly
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
