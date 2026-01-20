"""
File Upload Routes

Provides endpoints for uploading, downloading, and managing files in S3.
All actions are RBAC-protected and audit logged.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from botocore.exceptions import ClientError

from app.extensions import db
from app.models import FileUpload
from app.utils.rbac import require_role
from app.utils.audit import (
    log_upload_created,
    log_upload_downloaded,
    log_upload_deleted,
)
from app.storage.s3 import (
    upload_file,
    generate_presigned_download_url,
    delete_file,
    get_storage_config,
)

uploads_bp = Blueprint("uploads", __name__)


@uploads_bp.post("/uploads")
@require_role("admin")
def create_upload():
    """
    Upload a file to S3.
    
    Accepts multipart/form-data with a 'file' field.
    
    Returns:
        201: Upload successful with file metadata
        400: Validation error (empty file, size exceeded, invalid type)
        500: S3 upload failed
    """
    actor = request.current_user
    
    # Check for file in request
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    
    file = request.files["file"]
    
    if not file or file.filename == "":
        return jsonify({"error": "No file selected"}), 400
    
    # Read file data
    file_data = file.read()
    original_filename = file.filename
    content_type = file.content_type or "application/octet-stream"
    size_bytes = len(file_data)
    
    # Validate
    config = get_storage_config()
    
    if size_bytes == 0:
        return jsonify({"error": "File is empty"}), 400
    
    if size_bytes > config["max_upload_size"]:
        max_mb = config["max_upload_size"] / (1024 * 1024)
        return jsonify({"error": f"File exceeds maximum size of {max_mb:.0f}MB"}), 400
    
    if config["allowed_content_types"] and content_type not in config["allowed_content_types"]:
        return jsonify({
            "error": f"Content type '{content_type}' not allowed",
            "allowed_types": config["allowed_content_types"],
        }), 400
    
    try:
        # Upload to S3
        s3_key, bucket_name = upload_file(
            file_data=file_data,
            original_filename=original_filename,
            content_type=content_type,
            user_id=actor.id,
        )
        
        # Create database record
        upload = FileUpload(
            user_id=actor.id,
            original_filename=original_filename,
            filename=original_filename,  # Legacy field
            content_type=content_type,
            size_bytes=size_bytes,
            s3_bucket=bucket_name,
            s3_key=s3_key,
        )
        
        db.session.add(upload)
        db.session.commit()
        
        # Audit log
        log_upload_created(actor, upload)
        
        return jsonify({
            "message": "File uploaded successfully",
            "upload": upload.to_dict(),
        }), 201
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except ClientError as e:
        return jsonify({"error": f"S3 upload failed: {str(e)}"}), 500


@uploads_bp.get("/uploads")
@require_role("viewer")
def list_uploads():
    """
    List all uploads with pagination and filtering.
    
    Query params:
        page: Page number (default: 1)
        page_size: Items per page (default: 20, max: 100)
        search: Search by filename
        user_id: Filter by uploader
        include_deleted: Include soft-deleted files (default: false)
        
    Returns:
        200: Paginated list of uploads
    """
    query = FileUpload.query
    
    # Filter out deleted unless requested
    include_deleted = request.args.get("include_deleted", "false").lower() == "true"
    if not include_deleted:
        query = query.filter(FileUpload.deleted_at.is_(None))
    
    # Filter by user
    user_id = request.args.get("user_id", type=int)
    if user_id:
        query = query.filter(FileUpload.user_id == user_id)
    
    # Search by filename
    search = request.args.get("search")
    if search:
        query = query.filter(FileUpload.original_filename.ilike(f"%{search}%"))
    
    # Filter by content type
    content_type = request.args.get("content_type")
    if content_type:
        query = query.filter(FileUpload.content_type == content_type)
    
    # Sort
    sort = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc")
    if hasattr(FileUpload, sort):
        sort_col = getattr(FileUpload, sort)
        query = query.order_by(sort_col.desc() if order == "desc" else sort_col.asc())
    
    # Paginate
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)
    
    return jsonify({
        "items": [upload.to_dict() for upload in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
        "has_next": pagination.has_next,
        "has_prev": pagination.has_prev,
    })


@uploads_bp.get("/uploads/<int:upload_id>")
@require_role("viewer")
def get_upload(upload_id):
    """Get a single upload by ID."""
    upload = FileUpload.query.get(upload_id)
    
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    
    if upload.is_deleted:
        return jsonify({"error": "Upload has been deleted"}), 410
    
    return jsonify(upload.to_dict())


@uploads_bp.get("/uploads/<int:upload_id>/download")
@require_role("viewer")
def download_upload(upload_id):
    """
    Generate a presigned download URL for a file.
    
    Returns:
        200: Presigned URL with expiry time
        404: Upload not found
        410: Upload was deleted
        500: Failed to generate URL
    """
    actor = request.current_user
    upload = FileUpload.query.get(upload_id)
    
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    
    if upload.is_deleted:
        return jsonify({"error": "Upload has been deleted"}), 410
    
    try:
        config = get_storage_config()
        url = generate_presigned_download_url(
            s3_key=upload.s3_key,
            original_filename=upload.original_filename,
            expiry_seconds=config["presigned_url_expiry"],
        )
        
        # Audit log
        log_upload_downloaded(actor, upload)
        
        return jsonify({
            "download_url": url,
            "filename": upload.original_filename,
            "expires_in": config["presigned_url_expiry"],
        })
        
    except ClientError as e:
        return jsonify({"error": f"Failed to generate download URL: {str(e)}"}), 500


@uploads_bp.delete("/uploads/<int:upload_id>")
@require_role("admin")
def delete_upload(upload_id):
    """
    Delete an upload (soft delete in DB, delete from S3).
    
    Returns:
        200: Upload deleted
        404: Upload not found
        410: Already deleted
        500: S3 delete failed
    """
    actor = request.current_user
    upload = FileUpload.query.get(upload_id)
    
    if not upload:
        return jsonify({"error": "Upload not found"}), 404
    
    if upload.is_deleted:
        return jsonify({"error": "Upload already deleted"}), 410
    
    try:
        # Delete from S3
        delete_file(upload.s3_key)
        
        # Soft delete in DB
        upload.deleted_at = datetime.utcnow()
        db.session.commit()
        
        # Audit log
        log_upload_deleted(actor, upload)
        
        return jsonify({
            "message": "Upload deleted successfully",
            "upload_id": upload_id,
        })
        
    except ClientError as e:
        return jsonify({"error": f"Failed to delete from S3: {str(e)}"}), 500
