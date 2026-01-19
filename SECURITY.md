# Security Guide

## Environment-Based Security

This application enforces different security requirements based on the `ENVIRONMENT` variable.

### Production Mode (`ENVIRONMENT=production`)

The following environment variables are **required** and the app will refuse to start without them:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Flask session signing key |
| `JWT_SECRET_KEY` | JWT token signing key |
| `SQLALCHEMY_DATABASE_URI` | Database connection string |

Generate secure keys with:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### Development Mode (`ENVIRONMENT=development`)

Insecure default values are used for convenience. **Never use development mode in production.**

## JWT Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET_KEY` | (required in prod) | Secret for signing tokens |
| `JWT_ACCESS_TOKEN_EXPIRES` | `3600` | Token lifetime in seconds |
| `JWT_TOKEN_LOCATION` | `headers` | Token location (`headers`, `cookies`) |
| `JWT_HEADER_NAME` | `Authorization` | HTTP header name |
| `JWT_HEADER_TYPE` | `Bearer` | Token prefix |

## Secrets Management

### What NOT to commit
- `.env` files (already in `.gitignore`)
- Private keys or certificates
- API keys or tokens
- Database credentials

### Recommended practices
1. Use `.env.example` as a template (no real secrets)
2. Store production secrets in a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
3. Rotate secrets regularly
4. Use different secrets for each environment

## Database Security

- Never expose Postgres port (5432) to the internet in production
- Use strong passwords (not the default `password`)
- Enable SSL/TLS for database connections in production
- Restrict database user permissions to minimum required

## API Security

### Request ID Tracking
All requests receive an `X-Request-ID` header for tracing. Pass your own ID or one will be generated.

### Rate Limiting
Consider adding rate limiting for production deployments (e.g., Flask-Limiter).

### CORS
Configure CORS appropriately for your frontend domain in production.

## Reporting Security Issues

If you discover a security vulnerability, please report it privately rather than opening a public issue.
