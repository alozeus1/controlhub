"""
Integrations Service Layer

Business logic for webhook integrations and audit log exports.
"""
import csv
import io
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import requests

from app.extensions import db
from app.models import Integration, IntegrationLog, AuditExportJob, AuditLog, User
from app.utils.audit import log_action

logger = logging.getLogger(__name__)

INTEGRATION_TYPES = ["webhook", "siem"]
EXPORT_FORMATS = ["csv", "json", "jsonl"]
DESTINATION_TYPES = ["s3", "download"]

# Events that can be sent to integrations
INTEGRATION_EVENTS = [
    "audit.*",  # All audit events
    "user.created",
    "user.updated",
    "user.disabled",
    "user.login",
    "user.role_changed",
    "upload.created",
    "upload.deleted",
    "job.created",
    "job.completed",
    "job.failed",
    "approval.requested",
    "approval.approved",
    "approval.rejected",
    "policy.created",
    "policy.updated",
    "service_account.created",
    "api_key.created",
    "api_key.revoked",
]


class IntegrationService:
    """Service for managing integrations."""

    @staticmethod
    def list_integrations(
        page: int = 1,
        page_size: int = 20,
        integration_type: Optional[str] = None,
        is_enabled: Optional[bool] = None,
    ) -> dict:
        """List integrations with pagination and filters."""
        query = Integration.query

        if integration_type:
            query = query.filter(Integration.type == integration_type)

        if is_enabled is not None:
            query = query.filter(Integration.is_enabled == is_enabled)

        query = query.order_by(Integration.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [i.to_dict() for i in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_integration(integration_id: int) -> Optional[Integration]:
        """Get an integration by ID."""
        return Integration.query.get(integration_id)

    @staticmethod
    def create_integration(
        integration_type: str,
        name: str,
        config: Dict[str, Any],
        actor: User,
        description: Optional[str] = None,
        events: Optional[List[str]] = None,
    ) -> Integration:
        """Create a new integration."""
        if integration_type not in INTEGRATION_TYPES:
            raise ValueError(f"Unsupported integration type: {integration_type}")

        IntegrationService._validate_config(integration_type, config)

        integration = Integration(
            type=integration_type,
            name=name,
            description=description,
            config=config,
            events=events,
            is_enabled=True,
            created_by_id=actor.id,
        )
        db.session.add(integration)
        db.session.commit()

        log_action(
            action="integration.created",
            actor=actor,
            target_type="integration",
            target_id=integration.id,
            target_label=integration.name,
            details={"type": integration_type},
        )

        return integration

    @staticmethod
    def update_integration(
        integration: Integration,
        actor: User,
        name: Optional[str] = None,
        description: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
        events: Optional[List[str]] = None,
        is_enabled: Optional[bool] = None,
    ) -> Integration:
        """Update an integration."""
        changes = {}

        if name is not None and name != integration.name:
            changes["name"] = {"from": integration.name, "to": name}
            integration.name = name

        if description is not None:
            integration.description = description

        if config is not None:
            IntegrationService._validate_config(integration.type, config)
            changes["config"] = "updated"
            integration.config = config

        if events is not None:
            integration.events = events

        if is_enabled is not None and is_enabled != integration.is_enabled:
            changes["is_enabled"] = {"from": integration.is_enabled, "to": is_enabled}
            integration.is_enabled = is_enabled
            if is_enabled:
                integration.failure_count = 0  # Reset failure count on re-enable

        if changes:
            db.session.commit()
            log_action(
                action="integration.updated",
                actor=actor,
                target_type="integration",
                target_id=integration.id,
                target_label=integration.name,
                details=changes,
            )

        return integration

    @staticmethod
    def delete_integration(integration: Integration, actor: User) -> None:
        """Delete an integration and its logs."""
        integration_name = integration.name
        integration_id = integration.id

        # Delete logs first
        IntegrationLog.query.filter_by(integration_id=integration_id).delete()
        db.session.delete(integration)
        db.session.commit()

        log_action(
            action="integration.deleted",
            actor=actor,
            target_type="integration",
            target_id=integration_id,
            target_label=integration_name,
        )

    @staticmethod
    def test_integration(integration: Integration) -> Dict[str, Any]:
        """Send a test payload to verify integration configuration."""
        test_payload = {
            "event_type": "integration.test",
            "timestamp": datetime.utcnow().isoformat(),
            "source": "controlhub",
            "data": {
                "message": "This is a test event from ControlHub",
                "integration_id": integration.id,
                "integration_name": integration.name,
            },
        }

        result = IntegrationDeliveryService.deliver(integration, "integration.test", test_payload)
        return result

    @staticmethod
    def get_logs(
        integration_id: int,
        page: int = 1,
        page_size: int = 50,
        status: Optional[str] = None,
    ) -> dict:
        """Get delivery logs for an integration."""
        query = IntegrationLog.query.filter_by(integration_id=integration_id)

        if status:
            query = query.filter(IntegrationLog.status == status)

        query = query.order_by(IntegrationLog.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [log.to_dict() for log in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def _validate_config(integration_type: str, config: Dict[str, Any]) -> None:
        """Validate integration configuration."""
        if integration_type == "webhook":
            if not config.get("url"):
                raise ValueError("Webhook integration requires 'url'")
            url = config["url"]
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid webhook URL")

        elif integration_type == "siem":
            if not config.get("endpoint"):
                raise ValueError("SIEM integration requires 'endpoint'")


class IntegrationDeliveryService:
    """Service for delivering events to integrations."""

    MAX_FAILURES = 5  # Disable after this many consecutive failures

    @staticmethod
    def deliver(
        integration: Integration,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deliver an event to an integration."""
        start_time = time.time()

        try:
            if integration.type == "webhook":
                result = IntegrationDeliveryService._deliver_webhook(integration, payload)
            elif integration.type == "siem":
                result = IntegrationDeliveryService._deliver_siem(integration, payload)
            else:
                result = {"success": False, "error": f"Unsupported type: {integration.type}"}

            duration_ms = int((time.time() - start_time) * 1000)

            # Log the delivery
            log_entry = IntegrationLog(
                integration_id=integration.id,
                event_type=event_type,
                payload_summary=payload.get("data", {}).get("message", "")[:255] if payload.get("data") else None,
                status="success" if result.get("success") else "failed",
                response_code=result.get("status_code"),
                error_message=result.get("error"),
                duration_ms=duration_ms,
            )
            db.session.add(log_entry)

            # Update integration stats
            integration.last_triggered_at = datetime.utcnow()
            if result.get("success"):
                integration.failure_count = 0
            else:
                integration.failure_count += 1
                if integration.failure_count >= IntegrationDeliveryService.MAX_FAILURES:
                    integration.is_enabled = False
                    logger.warning(f"Integration {integration.id} disabled after {integration.failure_count} failures")

            db.session.commit()

            return result

        except Exception as e:
            logger.error(f"Integration delivery error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _deliver_webhook(integration: Integration, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver to a webhook endpoint."""
        url = integration.config.get("url")
        if not url:
            return {"success": False, "error": "No URL configured"}

        headers = {"Content-Type": "application/json"}

        # Add custom headers if configured
        custom_headers = integration.config.get("headers", {})
        headers.update(custom_headers)

        # Add auth if configured
        if integration.config.get("auth_type") == "bearer":
            token = integration.config.get("token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif integration.config.get("auth_type") == "api_key":
            api_key = integration.config.get("api_key")
            header_name = integration.config.get("api_key_header", "X-API-Key")
            if api_key:
                headers[header_name] = api_key

        # Add signature if secret is configured
        secret = integration.config.get("secret")
        if secret:
            import hashlib
            import hmac
            payload_bytes = json.dumps(payload).encode()
            signature = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
            headers["X-Signature"] = signature

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _deliver_siem(integration: Integration, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Deliver to a SIEM endpoint (CEF format)."""
        endpoint = integration.config.get("endpoint")
        if not endpoint:
            return {"success": False, "error": "No endpoint configured"}

        # Convert to CEF format
        cef_message = IntegrationDeliveryService._to_cef(payload)

        headers = {"Content-Type": "text/plain"}
        if integration.config.get("token"):
            headers["Authorization"] = f"Bearer {integration.config['token']}"

        try:
            response = requests.post(endpoint, data=cef_message, headers=headers, timeout=30)
            return {
                "success": response.status_code < 400,
                "status_code": response.status_code,
            }
        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _to_cef(payload: Dict[str, Any]) -> str:
        """Convert payload to CEF format."""
        event_type = payload.get("event_type", "unknown")
        timestamp = payload.get("timestamp", datetime.utcnow().isoformat())
        data = payload.get("data", {})

        # CEF format: CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
        severity = data.get("severity", 5)
        if isinstance(severity, str):
            severity_map = {"low": 3, "medium": 5, "high": 7, "critical": 10}
            severity = severity_map.get(severity, 5)

        cef = f"CEF:0|ControlHub|ControlHub|1.0|{event_type}|{event_type}|{severity}|"
        extensions = [f"rt={timestamp}"]
        
        if data.get("actor_email"):
            extensions.append(f"suser={data['actor_email']}")
        if data.get("target_label"):
            extensions.append(f"duser={data['target_label']}")
        if data.get("ip_address"):
            extensions.append(f"src={data['ip_address']}")

        cef += " ".join(extensions)
        return cef

    @staticmethod
    def broadcast_event(event_type: str, payload: Dict[str, Any]) -> None:
        """Broadcast an event to all matching enabled integrations."""
        integrations = Integration.query.filter_by(is_enabled=True).all()

        for integration in integrations:
            # Check if this integration wants this event
            if integration.events:
                # Check for exact match or wildcard
                if event_type not in integration.events and "audit.*" not in integration.events:
                    continue

            try:
                IntegrationDeliveryService.deliver(integration, event_type, payload)
            except Exception as e:
                logger.error(f"Failed to deliver to integration {integration.id}: {e}")


class AuditExportService:
    """Service for exporting audit logs."""

    @staticmethod
    def list_export_jobs(
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        """List audit export jobs."""
        query = AuditExportJob.query.order_by(AuditExportJob.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [job.to_dict() for job in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_export_job(job_id: int) -> Optional[AuditExportJob]:
        """Get an export job by ID."""
        return AuditExportJob.query.get(job_id)

    @staticmethod
    def create_export_job(
        name: str,
        export_format: str,
        destination_type: str,
        actor: User,
        destination_config: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        schedule: Optional[str] = None,
    ) -> AuditExportJob:
        """Create an audit export job."""
        if export_format not in EXPORT_FORMATS:
            raise ValueError(f"Unsupported format: {export_format}")
        if destination_type not in DESTINATION_TYPES:
            raise ValueError(f"Unsupported destination: {destination_type}")

        job = AuditExportJob(
            name=name,
            export_format=export_format,
            destination_type=destination_type,
            destination_config=destination_config,
            filters=filters,
            schedule=schedule,
            is_enabled=True,
            created_by_id=actor.id,
        )
        db.session.add(job)
        db.session.commit()

        log_action(
            action="audit_export.created",
            actor=actor,
            target_type="audit_export_job",
            target_id=job.id,
            target_label=job.name,
        )

        return job

    @staticmethod
    def run_export(
        job: AuditExportJob,
        actor: Optional[User] = None,
    ) -> Dict[str, Any]:
        """Run an audit export job and return the data."""
        filters = job.filters or {}

        # Build query
        query = AuditLog.query

        # Apply filters
        if filters.get("start_date"):
            start = datetime.fromisoformat(filters["start_date"])
            query = query.filter(AuditLog.created_at >= start)
        if filters.get("end_date"):
            end = datetime.fromisoformat(filters["end_date"])
            query = query.filter(AuditLog.created_at <= end)
        if filters.get("actions"):
            query = query.filter(AuditLog.action.in_(filters["actions"]))
        if filters.get("actor_email"):
            query = query.filter(AuditLog.actor_email.ilike(f"%{filters['actor_email']}%"))

        # Default to last 30 days if no date filter
        if not filters.get("start_date") and not filters.get("end_date"):
            start = datetime.utcnow() - timedelta(days=30)
            query = query.filter(AuditLog.created_at >= start)

        query = query.order_by(AuditLog.created_at.desc())
        records = query.all()

        # Convert to requested format
        if job.export_format == "csv":
            output = AuditExportService._to_csv(records)
            content_type = "text/csv"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        elif job.export_format == "json":
            output = json.dumps([r.to_dict() for r in records], indent=2)
            content_type = "application/json"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        else:  # jsonl
            output = "\n".join(json.dumps(r.to_dict()) for r in records)
            content_type = "application/x-ndjson"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"

        # Update job status
        job.last_run_at = datetime.utcnow()
        job.last_run_status = "success"
        job.last_run_records = len(records)
        db.session.commit()

        if actor:
            log_action(
                action="audit_export.executed",
                actor=actor,
                target_type="audit_export_job",
                target_id=job.id,
                target_label=job.name,
                details={"records": len(records)},
            )

        return {
            "data": output,
            "content_type": content_type,
            "filename": filename,
            "record_count": len(records),
        }

    @staticmethod
    def export_now(
        export_format: str,
        filters: Optional[Dict[str, Any]],
        actor: User,
    ) -> Dict[str, Any]:
        """Run an immediate one-time export without creating a job."""
        if export_format not in EXPORT_FORMATS:
            raise ValueError(f"Unsupported format: {export_format}")

        filters = filters or {}

        # Build query
        query = AuditLog.query

        if filters.get("start_date"):
            start = datetime.fromisoformat(filters["start_date"])
            query = query.filter(AuditLog.created_at >= start)
        if filters.get("end_date"):
            end = datetime.fromisoformat(filters["end_date"])
            query = query.filter(AuditLog.created_at <= end)
        if filters.get("actions"):
            query = query.filter(AuditLog.action.in_(filters["actions"]))

        # Default to last 30 days
        if not filters.get("start_date") and not filters.get("end_date"):
            start = datetime.utcnow() - timedelta(days=30)
            query = query.filter(AuditLog.created_at >= start)

        query = query.order_by(AuditLog.created_at.desc())
        records = query.all()

        if export_format == "csv":
            output = AuditExportService._to_csv(records)
            content_type = "text/csv"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
        elif export_format == "json":
            output = json.dumps([r.to_dict() for r in records], indent=2)
            content_type = "application/json"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        else:
            output = "\n".join(json.dumps(r.to_dict()) for r in records)
            content_type = "application/x-ndjson"
            filename = f"audit_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.jsonl"

        log_action(
            action="audit_export.adhoc",
            actor=actor,
            target_type="audit_log",
            details={"format": export_format, "records": len(records)},
        )

        return {
            "data": output,
            "content_type": content_type,
            "filename": filename,
            "record_count": len(records),
        }

    @staticmethod
    def delete_export_job(job: AuditExportJob, actor: User) -> None:
        """Delete an export job."""
        job_name = job.name
        job_id = job.id

        db.session.delete(job)
        db.session.commit()

        log_action(
            action="audit_export.deleted",
            actor=actor,
            target_type="audit_export_job",
            target_id=job_id,
            target_label=job_name,
        )

    @staticmethod
    def _to_csv(records: List[AuditLog]) -> str:
        """Convert audit records to CSV."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            "id", "created_at", "action", "actor_email", "target_type",
            "target_id", "target_label", "ip_address", "user_agent", "details"
        ])

        for record in records:
            writer.writerow([
                record.id,
                record.created_at.isoformat() if record.created_at else "",
                record.action,
                record.actor_email or "",
                record.target_type or "",
                record.target_id or "",
                record.target_label or "",
                record.ip_address or "",
                record.user_agent or "",
                json.dumps(record.details) if record.details else "",
            ])

        return output.getvalue()
