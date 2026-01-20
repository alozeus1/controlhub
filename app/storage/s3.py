"""
S3 Storage Module

Provides S3 client configuration and helper functions for file uploads/downloads.
Supports both LocalStack (local dev) and AWS S3 (production).

Configuration via environment variables:
- STORAGE_PROVIDER: "localstack" or "aws"
- S3_BUCKET_NAME: bucket name
- AWS_REGION: AWS region
- AWS_ENDPOINT_URL: LocalStack endpoint (only for localstack provider)
- AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY: credentials
"""

import os
import re
import uuid
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


def get_storage_config() -> dict:
    """Get storage configuration from environment."""
    return {
        "provider": os.environ.get("STORAGE_PROVIDER", "localstack"),
        "bucket_name": os.environ.get("S3_BUCKET_NAME", "controlhub-uploads"),
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "endpoint_url": os.environ.get("AWS_ENDPOINT_URL"),
        "max_upload_size": int(os.environ.get("MAX_UPLOAD_SIZE", 52428800)),  # 50MB
        "allowed_content_types": os.environ.get(
            "ALLOWED_CONTENT_TYPES",
            "image/jpeg,image/png,image/gif,image/webp,application/pdf,text/plain,text/csv,application/json,application/xml"
        ).split(",") if os.environ.get("ALLOWED_CONTENT_TYPES") else [],
        "presigned_url_expiry": int(os.environ.get("PRESIGNED_URL_EXPIRY", 900)),  # 15 min
    }


def build_s3_client():
    """
    Build and return an S3 client.
    
    For LocalStack: uses endpoint_url from config
    For AWS: uses default credential chain (IAM roles, env vars, ~/.aws/credentials)
    """
    config = get_storage_config()
    
    client_kwargs = {
        "service_name": "s3",
        "region_name": config["region"],
        "config": Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"}  # Required for LocalStack
        ),
    }
    
    # Use endpoint URL for LocalStack
    if config["provider"] == "localstack" and config["endpoint_url"]:
        client_kwargs["endpoint_url"] = config["endpoint_url"]
        # For LocalStack, use test credentials if not set
        client_kwargs["aws_access_key_id"] = os.environ.get("AWS_ACCESS_KEY_ID", "test")
        client_kwargs["aws_secret_access_key"] = os.environ.get("AWS_SECRET_ACCESS_KEY", "test")
    
    return boto3.client(**client_kwargs)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for S3 keys.
    Removes/replaces special characters, preserves extension.
    """
    if not filename:
        return "unnamed"
    
    # Get extension
    parts = filename.rsplit(".", 1)
    name = parts[0]
    ext = parts[1] if len(parts) > 1 else ""
    
    # Remove/replace unsafe characters
    name = re.sub(r"[^\w\-.]", "_", name)
    name = re.sub(r"_+", "_", name)  # Collapse multiple underscores
    name = name.strip("_")[:100]  # Limit length
    
    if not name:
        name = "file"
    
    return f"{name}.{ext}" if ext else name


def generate_s3_key(original_filename: str, user_id: Optional[int] = None) -> str:
    """
    Generate a unique S3 object key with safe naming.
    
    Format: uploads/<yyyy>/<mm>/<uuid>_<sanitized_filename>
    
    Args:
        original_filename: Original filename from upload
        user_id: Optional user ID for namespacing
        
    Returns:
        S3 object key string
    """
    now = datetime.utcnow()
    unique_id = uuid.uuid4().hex[:12]
    safe_filename = sanitize_filename(original_filename)
    
    # Format: uploads/2026/01/abc123def456_document.pdf
    key = f"uploads/{now.year}/{now.month:02d}/{unique_id}_{safe_filename}"
    
    return key


def upload_file(
    file_data: bytes,
    original_filename: str,
    content_type: str,
    user_id: Optional[int] = None,
) -> Tuple[str, str]:
    """
    Upload a file to S3.
    
    Args:
        file_data: File content as bytes
        original_filename: Original filename
        content_type: MIME type
        user_id: Optional user ID
        
    Returns:
        Tuple of (s3_key, bucket_name)
        
    Raises:
        ValueError: If file is empty or exceeds size limit
        ClientError: If S3 upload fails
    """
    config = get_storage_config()
    
    # Validation
    if not file_data:
        raise ValueError("File is empty")
    
    if len(file_data) > config["max_upload_size"]:
        max_mb = config["max_upload_size"] / (1024 * 1024)
        raise ValueError(f"File exceeds maximum size of {max_mb:.0f}MB")
    
    if config["allowed_content_types"] and content_type not in config["allowed_content_types"]:
        raise ValueError(f"Content type '{content_type}' not allowed")
    
    # Generate key and upload
    s3_key = generate_s3_key(original_filename, user_id)
    bucket_name = config["bucket_name"]
    
    client = build_s3_client()
    client.put_object(
        Bucket=bucket_name,
        Key=s3_key,
        Body=file_data,
        ContentType=content_type,
        Metadata={
            "original-filename": quote(original_filename),
            "uploaded-by": str(user_id) if user_id else "anonymous",
        }
    )
    
    return s3_key, bucket_name


def generate_presigned_download_url(
    s3_key: str,
    original_filename: Optional[str] = None,
    expiry_seconds: Optional[int] = None,
) -> str:
    """
    Generate a presigned URL for downloading a file.
    
    Args:
        s3_key: S3 object key
        original_filename: Optional filename for Content-Disposition header
        expiry_seconds: URL expiry in seconds (default from config)
        
    Returns:
        Presigned URL string
    """
    config = get_storage_config()
    expiry = expiry_seconds or config["presigned_url_expiry"]
    
    client = build_s3_client()
    
    params = {
        "Bucket": config["bucket_name"],
        "Key": s3_key,
    }
    
    # Add Content-Disposition to trigger download with original filename
    if original_filename:
        safe_filename = quote(original_filename)
        params["ResponseContentDisposition"] = f'attachment; filename="{safe_filename}"'
    
    url = client.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expiry,
    )
    
    return url


def delete_file(s3_key: str) -> bool:
    """
    Delete a file from S3.
    
    Args:
        s3_key: S3 object key
        
    Returns:
        True if deleted, False if not found
    """
    config = get_storage_config()
    client = build_s3_client()
    
    try:
        client.delete_object(
            Bucket=config["bucket_name"],
            Key=s3_key,
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return False
        raise


def file_exists(s3_key: str) -> bool:
    """Check if a file exists in S3."""
    config = get_storage_config()
    client = build_s3_client()
    
    try:
        client.head_object(
            Bucket=config["bucket_name"],
            Key=s3_key,
        )
        return True
    except ClientError:
        return False


def get_file_metadata(s3_key: str) -> Optional[dict]:
    """
    Get metadata for a file in S3.
    
    Returns:
        Dict with ContentType, ContentLength, LastModified, Metadata
        or None if file doesn't exist
    """
    config = get_storage_config()
    client = build_s3_client()
    
    try:
        response = client.head_object(
            Bucket=config["bucket_name"],
            Key=s3_key,
        )
        return {
            "content_type": response.get("ContentType"),
            "content_length": response.get("ContentLength"),
            "last_modified": response.get("LastModified"),
            "metadata": response.get("Metadata", {}),
        }
    except ClientError:
        return None
