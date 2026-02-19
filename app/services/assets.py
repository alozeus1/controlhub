"""
Assets Service Layer

Business logic for IT asset inventory management.
"""
import re
from datetime import datetime, date
from typing import Optional, List, Dict, Any

from app.extensions import db
from app.models import Asset, AssetHistory, User
from app.utils.audit import log_action

ASSET_TYPES = ["server", "laptop", "desktop", "network", "mobile", "software", "other"]
ASSET_STATUSES = ["active", "inactive", "maintenance", "retired", "disposed"]


class AssetService:
    """Service for managing IT assets."""

    @staticmethod
    def list_assets(
        page: int = 1,
        page_size: int = 20,
        asset_type: Optional[str] = None,
        status: Optional[str] = None,
        department: Optional[str] = None,
        assigned_to_id: Optional[int] = None,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> dict:
        """List assets with pagination and filters."""
        query = Asset.query

        if asset_type:
            query = query.filter(Asset.asset_type == asset_type)

        if status:
            query = query.filter(Asset.status == status)

        if department:
            query = query.filter(Asset.department == department)

        if assigned_to_id is not None:
            if assigned_to_id == 0:
                query = query.filter(Asset.assigned_to_id.is_(None))
            else:
                query = query.filter(Asset.assigned_to_id == assigned_to_id)

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Asset.asset_tag.ilike(search_term),
                    Asset.name.ilike(search_term),
                    Asset.serial_number.ilike(search_term),
                    Asset.ip_address.ilike(search_term),
                )
            )

        # Tag filtering (assets that have ALL specified tags)
        if tags:
            for tag in tags:
                query = query.filter(Asset.tags.contains([tag]))

        query = query.order_by(Asset.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [a.to_dict() for a in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_asset(asset_id: int) -> Optional[Asset]:
        """Get an asset by ID."""
        return Asset.query.get(asset_id)

    @staticmethod
    def get_asset_by_tag(asset_tag: str) -> Optional[Asset]:
        """Get an asset by its tag."""
        return Asset.query.filter_by(asset_tag=asset_tag).first()

    @staticmethod
    def generate_asset_tag(asset_type: str) -> str:
        """Generate a unique asset tag."""
        prefix_map = {
            "server": "SRV",
            "laptop": "LPT",
            "desktop": "DSK",
            "network": "NET",
            "mobile": "MOB",
            "software": "SFT",
            "other": "OTH",
        }
        prefix = prefix_map.get(asset_type, "AST")
        
        # Find the highest existing number for this prefix
        existing = Asset.query.filter(Asset.asset_tag.like(f"{prefix}-%")).all()
        max_num = 0
        for asset in existing:
            match = re.match(rf"{prefix}-(\d+)", asset.asset_tag)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
        
        return f"{prefix}-{max_num + 1:04d}"

    @staticmethod
    def create_asset(
        name: str,
        asset_type: str,
        actor: User,
        asset_tag: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        department: Optional[str] = None,
        assigned_to_id: Optional[int] = None,
        manufacturer: Optional[str] = None,
        model: Optional[str] = None,
        serial_number: Optional[str] = None,
        ip_address: Optional[str] = None,
        mac_address: Optional[str] = None,
        purchase_date: Optional[date] = None,
        warranty_expiry: Optional[date] = None,
        attributes: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
    ) -> Asset:
        """Create a new asset."""
        if asset_type not in ASSET_TYPES:
            raise ValueError(f"Invalid asset type: {asset_type}")

        # Generate tag if not provided
        if not asset_tag:
            asset_tag = AssetService.generate_asset_tag(asset_type)
        else:
            # Check uniqueness
            if Asset.query.filter_by(asset_tag=asset_tag).first():
                raise ValueError(f"Asset tag '{asset_tag}' already exists")

        asset = Asset(
            asset_tag=asset_tag,
            name=name,
            asset_type=asset_type,
            status="active",
            description=description,
            location=location,
            department=department,
            assigned_to_id=assigned_to_id,
            manufacturer=manufacturer,
            model=model,
            serial_number=serial_number,
            ip_address=ip_address,
            mac_address=mac_address,
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            attributes=attributes,
            tags=tags,
            created_by_id=actor.id,
        )
        db.session.add(asset)
        db.session.flush()

        # Record history
        AssetService._record_history(asset, "created", None, actor)

        db.session.commit()

        log_action(
            action="asset.created",
            actor=actor,
            target_type="asset",
            target_id=asset.id,
            target_label=asset.asset_tag,
            details={"name": name, "type": asset_type},
        )

        return asset

    @staticmethod
    def update_asset(
        asset: Asset,
        actor: User,
        **kwargs,
    ) -> Asset:
        """Update an asset."""
        changes = {}
        
        updatable_fields = [
            "name", "description", "location", "department", "assigned_to_id",
            "manufacturer", "model", "serial_number", "ip_address", "mac_address",
            "purchase_date", "warranty_expiry", "attributes", "tags"
        ]

        for field in updatable_fields:
            if field in kwargs and kwargs[field] is not None:
                old_value = getattr(asset, field)
                new_value = kwargs[field]
                
                # Handle date conversion
                if field in ("purchase_date", "warranty_expiry") and isinstance(new_value, str):
                    new_value = datetime.strptime(new_value, "%Y-%m-%d").date() if new_value else None
                
                if old_value != new_value:
                    changes[field] = {"from": str(old_value) if old_value else None, "to": str(new_value) if new_value else None}
                    setattr(asset, field, new_value)

        # Handle status separately for special tracking
        if "status" in kwargs and kwargs["status"] != asset.status:
            old_status = asset.status
            new_status = kwargs["status"]
            if new_status not in ASSET_STATUSES:
                raise ValueError(f"Invalid status: {new_status}")
            changes["status"] = {"from": old_status, "to": new_status}
            asset.status = new_status

        if changes:
            # Determine action type
            if "status" in changes:
                action = "status_changed"
            elif "assigned_to_id" in changes:
                action = "assigned" if kwargs.get("assigned_to_id") else "unassigned"
            else:
                action = "updated"

            AssetService._record_history(asset, action, changes, actor)
            db.session.commit()

            log_action(
                action=f"asset.{action}",
                actor=actor,
                target_type="asset",
                target_id=asset.id,
                target_label=asset.asset_tag,
                details=changes,
            )

        return asset

    @staticmethod
    def delete_asset(asset: Asset, actor: User) -> None:
        """Delete an asset and its history."""
        asset_tag = asset.asset_tag
        asset_id = asset.id

        # Delete history first
        AssetHistory.query.filter_by(asset_id=asset_id).delete()
        db.session.delete(asset)
        db.session.commit()

        log_action(
            action="asset.deleted",
            actor=actor,
            target_type="asset",
            target_id=asset_id,
            target_label=asset_tag,
        )

    @staticmethod
    def get_history(
        asset_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> dict:
        """Get asset change history."""
        query = AssetHistory.query.filter_by(asset_id=asset_id)
        query = query.order_by(AssetHistory.created_at.desc())
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)

        return {
            "items": [h.to_dict() for h in pagination.items],
            "total": pagination.total,
            "page": pagination.page,
            "page_size": pagination.per_page,
            "pages": pagination.pages,
        }

    @staticmethod
    def get_stats() -> dict:
        """Get asset statistics."""
        total = Asset.query.count()
        by_type = db.session.query(
            Asset.asset_type, db.func.count(Asset.id)
        ).group_by(Asset.asset_type).all()
        by_status = db.session.query(
            Asset.status, db.func.count(Asset.id)
        ).group_by(Asset.status).all()
        by_department = db.session.query(
            Asset.department, db.func.count(Asset.id)
        ).filter(Asset.department.isnot(None)).group_by(Asset.department).all()

        # Warranty expiring soon (next 30 days)
        thirty_days = datetime.utcnow().date()
        from datetime import timedelta
        expiring_soon = Asset.query.filter(
            Asset.warranty_expiry.isnot(None),
            Asset.warranty_expiry <= thirty_days + timedelta(days=30),
            Asset.warranty_expiry >= thirty_days,
        ).count()

        return {
            "total": total,
            "by_type": {t: c for t, c in by_type},
            "by_status": {s: c for s, c in by_status},
            "by_department": {d: c for d, c in by_department if d},
            "warranty_expiring_soon": expiring_soon,
        }

    @staticmethod
    def get_departments() -> List[str]:
        """Get list of unique departments."""
        results = db.session.query(Asset.department).filter(
            Asset.department.isnot(None)
        ).distinct().all()
        return sorted([r[0] for r in results if r[0]])

    @staticmethod
    def get_all_tags() -> List[str]:
        """Get list of all unique tags used."""
        assets = Asset.query.filter(Asset.tags.isnot(None)).all()
        all_tags = set()
        for asset in assets:
            if asset.tags:
                all_tags.update(asset.tags)
        return sorted(list(all_tags))

    @staticmethod
    def _record_history(
        asset: Asset,
        action: str,
        changes: Optional[Dict[str, Any]],
        actor: User,
    ) -> None:
        """Record a history entry for an asset."""
        history = AssetHistory(
            asset_id=asset.id,
            action=action,
            changes=changes,
            actor_id=actor.id if actor else None,
            actor_email=actor.email if actor else None,
        )
        db.session.add(history)
