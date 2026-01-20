# Storage Documentation

*Web Forx ControlHub by Web Forx Global Inc.*

This document describes the file storage system, including S3 integration, security considerations, and configuration options.

---

## Overview

ControlHub uses Amazon S3 (or S3-compatible storage) for file uploads. The system supports:

- **LocalStack** for local development (no AWS account required)
- **AWS S3** for production environments

All file operations are:
- RBAC-protected (admin+ for upload/delete, viewer+ for list/download)
- Audit logged
- Validated for size and content type

---

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   React UI      │────▶│   Flask API     │────▶│   S3 Storage    │
│   (Uploads)     │     │   (Validation)  │     │   (LocalStack/  │
│                 │     │   (Audit Log)   │     │    AWS)         │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**Upload Flow:**
1. User selects file in UI
2. UI sends multipart POST to `/admin/uploads`
3. API validates file (size, type)
4. API uploads to S3 with generated key
5. API stores metadata in PostgreSQL
6. API logs action to audit_log table

**Download Flow:**
1. User clicks Download in UI
2. UI requests presigned URL from `/admin/uploads/{id}/download`
3. API generates 15-minute presigned URL
4. API logs download action
5. UI opens presigned URL in new tab

---

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `STORAGE_PROVIDER` | `localstack` or `aws` | `localstack` | No |
| `S3_BUCKET_NAME` | S3 bucket name | `controlhub-uploads` | No |
| `AWS_REGION` | AWS region | `us-east-1` | No |
| `AWS_ENDPOINT_URL` | LocalStack endpoint | - | LocalStack only |
| `AWS_ACCESS_KEY_ID` | AWS access key | `test` (LocalStack) | AWS only |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | `test` (LocalStack) | AWS only |
| `MAX_UPLOAD_SIZE` | Max file size in bytes | `52428800` (50MB) | No |
| `ALLOWED_CONTENT_TYPES` | Comma-separated MIME types | Common types | No |
| `PRESIGNED_URL_EXPIRY` | URL expiry in seconds | `900` (15 min) | No |

### LocalStack (Development)

LocalStack is automatically configured in `docker-compose.yml`:

```yaml
localstack:
  image: localstack/localstack:3.0
  ports:
    - "4566:4566"
  environment:
    SERVICES: s3
    S3_BUCKET_NAME: controlhub-uploads
```

The bucket is created automatically on startup via `scripts/localstack/init-s3.sh`.

### AWS S3 (Production)

For production, set these environment variables:

```bash
STORAGE_PROVIDER=aws
S3_BUCKET_NAME=your-bucket-name
AWS_REGION=us-east-1
# Use IAM roles or set credentials
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

**Recommended AWS Setup:**
1. Create an S3 bucket with versioning enabled
2. Create an IAM role with minimal permissions
3. Use IAM roles for ECS/EKS instead of hardcoded credentials

---

## Security

### Access Control

| Action | Required Role | Audit Logged |
|--------|--------------|--------------|
| List uploads | viewer+ | No |
| Download file | viewer+ | Yes |
| Upload file | admin+ | Yes |
| Delete file | admin+ | Yes |

### S3 Key Generation

Files are stored with secure, non-guessable keys:

```
uploads/<year>/<month>/<uuid>_<sanitized_filename>
```

Example: `uploads/2026/01/a1b2c3d4e5f6_document.pdf`

### Presigned URLs

- **Expiry**: 15 minutes (configurable via `PRESIGNED_URL_EXPIRY`)
- **Signature**: AWS Signature v4
- **Headers**: Content-Disposition forces download with original filename

### File Validation

**Size Limits:**
- Default maximum: 50MB
- Configurable via `MAX_UPLOAD_SIZE`

**Content Type Whitelist:**
- Images: `image/jpeg`, `image/png`, `image/gif`, `image/webp`
- Documents: `application/pdf`
- Text: `text/plain`, `text/csv`
- Data: `application/json`, `application/xml`

### Soft Deletes

Files are soft-deleted (marked with `deleted_at` timestamp) to:
- Maintain audit trail
- Allow recovery if needed
- Support compliance requirements

The S3 object is deleted immediately, but the database record persists.

---

## API Endpoints

### POST /admin/uploads
Upload a file.

**Request:**
```
Content-Type: multipart/form-data

file: <binary data>
```

**Response:**
```json
{
  "message": "File uploaded successfully",
  "upload": {
    "id": 1,
    "original_filename": "document.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12345,
    "s3_key": "uploads/2026/01/...",
    "created_at": "2026-01-20T12:00:00"
  }
}
```

### GET /admin/uploads
List uploads with pagination.

**Query Parameters:**
- `page`: Page number (default: 1)
- `page_size`: Items per page (default: 20, max: 100)
- `search`: Filter by filename
- `user_id`: Filter by uploader
- `include_deleted`: Include soft-deleted (default: false)

### GET /admin/uploads/{id}/download
Get presigned download URL.

**Response:**
```json
{
  "download_url": "https://...",
  "filename": "document.pdf",
  "expires_in": 900
}
```

### DELETE /admin/uploads/{id}
Delete an upload (soft delete).

---

## Troubleshooting

### LocalStack Issues

**Bucket not created:**
```bash
# Check LocalStack logs
docker compose logs localstack | grep -i bucket

# Manually create bucket
aws --endpoint-url=http://localhost:4566 s3 mb s3://controlhub-uploads
```

**Connection refused:**
- Ensure LocalStack is healthy: `docker compose ps`
- Check endpoint URL uses Docker network hostname (`localstack`) not `localhost`

### Upload Failures

**File too large:**
- Increase `MAX_UPLOAD_SIZE` or reduce file size

**Content type not allowed:**
- Add type to `ALLOWED_CONTENT_TYPES` or clear the variable to allow all

**S3 error:**
- Check AWS credentials
- Verify bucket exists
- Check IAM permissions

### Download Issues

**URL expired:**
- Presigned URLs expire after 15 minutes
- Request a new download URL

**CORS error:**
- Ensure bucket CORS is configured (done automatically for LocalStack)
- For AWS, configure CORS in S3 console

---

## Data Retention

By default, uploads are retained indefinitely. Consider implementing:

1. **Lifecycle policies** in S3 for automatic cleanup
2. **Scheduled cleanup job** for soft-deleted files older than N days
3. **Compliance holds** for regulated data

---

*Web Forx ControlHub by Web Forx Global Inc.*  
*https://www.webforxtech.com/*
