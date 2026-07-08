"""
Governance Routes

Provides endpoints for managing policies and approval requests.
"""
from datetime import datetime
from flask import Blueprint, jsonify, request

from app.extensions import db
from app.models import Policy, ApprovalRequest, ApprovalDecision, ROLE_LEVELS
from app.utils.rbac import require_role
from app.utils.audit import log_action

governance_bp = Blueprint("governance", __name__)


# =============================================================================
# POLICY ENDPOINTS
# =============================================================================

@governance_bp.get("/policies")
@require_role("admin")
def list_policies():
    """List all policies with optional filtering."""
    query = Policy.query

    # Filters
    action = request.args.get("action")
    if action:
        query = query.filter(Policy.action == action)

    is_active = request.args.get("is_active")
    if is_active is not None:
        query = query.filter(Policy.is_active == (is_active.lower() == "true"))

    requires_approval = request.args.get("requires_approval")
    if requires_approval is not None:
        query = query.filter(Policy.requires_approval == (requires_approval.lower() == "true"))

    query = query.order_by(Policy.created_at.desc())

    # Paginate
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [p.to_dict() for p in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@governance_bp.get("/policies/<int:policy_id>")
@require_role("admin")
def get_policy(policy_id):
    """Get a single policy by ID."""
    policy = Policy.query.get(policy_id)
    if not policy:
        return jsonify({"error": "Policy not found"}), 404
    return jsonify(policy.to_dict())


@governance_bp.post("/policies")
@require_role("admin")
def create_policy():
    """Create a new policy."""
    actor = request.current_user
    data = request.get_json(silent=True) or {}

    # Validation
    name = data.get("name", "").strip()
    action = data.get("action", "").strip()

    if not name or not action:
        return jsonify({"error": "Name and action are required"}), 400

    # Check for duplicate action policy
    existing = Policy.query.filter_by(action=action, is_active=True).first()
    if existing:
        return jsonify({"error": f"An active policy for action '{action}' already exists"}), 400

    policy = Policy(
        name=name,
        description=data.get("description", ""),
        action=action,
        environment=data.get("environment", "all"),
        required_role=data.get("required_role", "admin"),
        requires_approval=data.get("requires_approval", False),
        approvals_required=data.get("approvals_required", 1),
        approver_role=data.get("approver_role", "admin"),
        is_active=data.get("is_active", True),
        created_by=actor.id,
    )

    db.session.add(policy)
    db.session.commit()

    log_action(
        action="policy.created",
        actor=actor,
        target_type="policy",
        target_id=policy.id,
        target_label=policy.name,
        details={"policy_action": policy.action, "requires_approval": policy.requires_approval},
    )

    return jsonify({"message": "Policy created", "policy": policy.to_dict()}), 201


@governance_bp.patch("/policies/<int:policy_id>")
@require_role("admin")
def update_policy(policy_id):
    """Update a policy."""
    actor = request.current_user
    policy = Policy.query.get(policy_id)

    if not policy:
        return jsonify({"error": "Policy not found"}), 404

    data = request.get_json(silent=True) or {}
    changes = {}

    for field in ["name", "description", "environment", "required_role", 
                  "requires_approval", "approvals_required", "approver_role", "is_active"]:
        if field in data:
            old_value = getattr(policy, field)
            new_value = data[field]
            if old_value != new_value:
                setattr(policy, field, new_value)
                changes[field] = {"from": old_value, "to": new_value}

    if changes:
        db.session.commit()
        log_action(
            action="policy.updated",
            actor=actor,
            target_type="policy",
            target_id=policy.id,
            target_label=policy.name,
            details={"changes": changes},
        )
        return jsonify({"message": "Policy updated", "policy": policy.to_dict(), "changes": changes})

    return jsonify({"message": "No changes made", "policy": policy.to_dict()})


@governance_bp.delete("/policies/<int:policy_id>")
@require_role("admin")
def delete_policy(policy_id):
    """Soft delete a policy by deactivating it."""
    actor = request.current_user
    policy = Policy.query.get(policy_id)

    if not policy:
        return jsonify({"error": "Policy not found"}), 404

    policy.is_active = False
    db.session.commit()

    log_action(
        action="policy.deleted",
        actor=actor,
        target_type="policy",
        target_id=policy.id,
        target_label=policy.name,
    )

    return jsonify({"message": "Policy deactivated", "policy_id": policy_id})


# =============================================================================
# APPROVAL REQUEST ENDPOINTS
# =============================================================================

@governance_bp.get("/approvals")
@require_role("admin")
def list_approvals():
    """List approval requests with filtering."""
    query = ApprovalRequest.query

    # Filters
    status = request.args.get("status")
    if status:
        query = query.filter(ApprovalRequest.status == status)

    action = request.args.get("action")
    if action:
        query = query.filter(ApprovalRequest.action == action)

    requester_id = request.args.get("requester_id", type=int)
    if requester_id:
        query = query.filter(ApprovalRequest.requester_id == requester_id)

    query = query.order_by(ApprovalRequest.created_at.desc())

    # Paginate
    page = request.args.get("page", 1, type=int)
    page_size = min(request.args.get("page_size", 20, type=int), 100)
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)

    return jsonify({
        "items": [r.to_dict() for r in pagination.items],
        "total": pagination.total,
        "page": pagination.page,
        "page_size": pagination.per_page,
        "pages": pagination.pages,
    })


@governance_bp.get("/approvals/<int:request_id>")
@require_role("admin")
def get_approval(request_id):
    """Get a single approval request with decisions."""
    approval = ApprovalRequest.query.get(request_id)
    if not approval:
        return jsonify({"error": "Approval request not found"}), 404

    result = approval.to_dict()
    result["decisions"] = [d.to_dict() for d in approval.decisions]
    return jsonify(result)


@governance_bp.post("/approvals/<int:request_id>/approve")
@require_role("admin")
def approve_request(request_id):
    """Approve an approval request."""
    actor = request.current_user
    approval = ApprovalRequest.query.get(request_id)

    if not approval:
        return jsonify({"error": "Approval request not found"}), 404

    if approval.status != "pending":
        return jsonify({"error": f"Request is already {approval.status}"}), 400

    # Check if actor has required role to approve
    policy = approval.policy
    approver_level = ROLE_LEVELS.get(policy.approver_role, 0)
    if actor.role_level < approver_level:
        return jsonify({"error": f"Requires {policy.approver_role} role to approve"}), 403

    # Check for double-approve
    existing_decision = ApprovalDecision.query.filter_by(
        request_id=request_id, approver_id=actor.id
    ).first()
    if existing_decision:
        return jsonify({"error": "You have already made a decision on this request"}), 400

    # Cannot approve own request
    if approval.requester_id == actor.id:
        return jsonify({"error": "Cannot approve your own request"}), 400

    data = request.get_json(silent=True) or {}

    # Record decision
    decision = ApprovalDecision(
        request_id=request_id,
        approver_id=actor.id,
        decision="approved",
        comment=data.get("comment", ""),
    )
    db.session.add(decision)

    approval.approvals_received += 1

    # Check if fully approved
    if approval.approvals_received >= policy.approvals_required:
        approval.status = "approved"
        approval.resolved_at = datetime.utcnow()

        log_action(
            action="approval.approved",
            actor=actor,
            target_type="approval_request",
            target_id=approval.id,
            target_label=f"{approval.action} on {approval.target_label}",
            details={"final": True},
        )

        # Execute the original action
        execution_result = execute_approved_action(approval, actor)

        db.session.commit()
        return jsonify({
            "message": "Request approved and executed",
            "approval": approval.to_dict(),
            "execution_result": execution_result,
        })
    else:
        log_action(
            action="approval.approved",
            actor=actor,
            target_type="approval_request",
            target_id=approval.id,
            target_label=f"{approval.action} on {approval.target_label}",
            details={"final": False, "approvals_received": approval.approvals_received},
        )

        db.session.commit()
        return jsonify({
            "message": f"Approval recorded ({approval.approvals_received}/{policy.approvals_required})",
            "approval": approval.to_dict(),
        })


@governance_bp.post("/approvals/<int:request_id>/reject")
@require_role("admin")
def reject_request(request_id):
    """Reject an approval request."""
    actor = request.current_user
    approval = ApprovalRequest.query.get(request_id)

    if not approval:
        return jsonify({"error": "Approval request not found"}), 404

    if approval.status != "pending":
        return jsonify({"error": f"Request is already {approval.status}"}), 400

    # Check if actor has required role
    policy = approval.policy
    approver_level = ROLE_LEVELS.get(policy.approver_role, 0)
    if actor.role_level < approver_level:
        return jsonify({"error": f"Requires {policy.approver_role} role to reject"}), 403

    # Check for double-decision
    existing_decision = ApprovalDecision.query.filter_by(
        request_id=request_id, approver_id=actor.id
    ).first()
    if existing_decision:
        return jsonify({"error": "You have already made a decision on this request"}), 400

    data = request.get_json(silent=True) or {}

    # Record decision
    decision = ApprovalDecision(
        request_id=request_id,
        approver_id=actor.id,
        decision="rejected",
        comment=data.get("comment", ""),
    )
    db.session.add(decision)

    # Reject immediately
    approval.status = "rejected"
    approval.resolved_at = datetime.utcnow()
    db.session.commit()

    log_action(
        action="approval.rejected",
        actor=actor,
        target_type="approval_request",
        target_id=approval.id,
        target_label=f"{approval.action} on {approval.target_label}",
        details={"comment": data.get("comment", "")},
    )

    return jsonify({
        "message": "Request rejected",
        "approval": approval.to_dict(),
    })


# =============================================================================
# POLICY CHECK HELPER
# =============================================================================

def check_policy(action: str, actor, target_type: str = None, target_id: int = None,
                 target_label: str = None, request_data: dict = None):
    """
    Check if an action requires approval based on active policies.
    
    Returns:
        tuple: (requires_approval: bool, policy: Policy or None, approval_request: ApprovalRequest or None)
    """
    policy = Policy.query.filter_by(action=action, is_active=True).first()

    if not policy:
        return False, None, None

    if not policy.requires_approval:
        return False, policy, None

    # Create approval request
    approval = ApprovalRequest(
        policy_id=policy.id,
        requester_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        request_data=request_data,
        status="pending",
    )
    db.session.add(approval)
    db.session.commit()

    log_action(
        action="approval.requested",
        actor=actor,
        target_type="approval_request",
        target_id=approval.id,
        target_label=f"{action} on {target_label}",
        details={"policy_id": policy.id, "policy_name": policy.name},
    )

    return True, policy, approval


def execute_approved_action(approval: ApprovalRequest, executor):
    """
    Execute an approved action.
    
    This function handles the actual execution of various protected actions
    after they've been approved.
    """
    action = approval.action
    target_id = approval.target_id
    request_data = approval.request_data or {}

    if action == "upload.delete":
        from app.models import FileUpload
        from app.storage.s3 import delete_file
        from app.utils.audit import log_upload_deleted

        upload = FileUpload.query.get(target_id)
        if upload and not upload.is_deleted:
            delete_file(upload.s3_key)
            upload.deleted_at = datetime.utcnow()
            log_upload_deleted(executor, upload)
            return {"success": True, "message": f"Deleted upload: {upload.original_filename}"}
        return {"success": False, "message": "Upload not found or already deleted"}

    elif action == "user.role_change":
        from app.models import User
        from app.utils.audit import log_role_changed

        user = User.query.get(target_id)
        if user:
            old_role = user.role
            new_role = request_data.get("new_role")
            if new_role:
                user.role = new_role
                log_role_changed(executor, user, old_role, new_role)
                return {"success": True, "message": f"Changed role for {user.email} from {old_role} to {new_role}"}
        return {"success": False, "message": "User not found or invalid role"}

    elif action == "user.disable":
        from app.models import User
        from app.utils.audit import log_user_disabled

        user = User.query.get(target_id)
        if user and user.is_active:
            user.is_active = False
            log_user_disabled(executor, user)
            return {"success": True, "message": f"Disabled user: {user.email}"}
        return {"success": False, "message": "User not found or already disabled"}

    elif action == "job.cancel":
        from app.models import Job

        job = Job.query.get(target_id)
        if job and job.status not in ["completed", "cancelled"]:
            job.status = "cancelled"
            log_action(
                action="job.cancelled",
                actor=executor,
                target_type="job",
                target_id=job.id,
                target_label=job.job_id,
            )
            return {"success": True, "message": f"Cancelled job: {job.job_id}"}
        return {"success": False, "message": "Job not found or already completed/cancelled"}

    elif action == "people.terminate":
        from app.models import Person
        person = Person.query.get(target_id)
        if not person:
            return {"success": False, "message": "Person not found"}
        employment = person.active_employment
        if not employment:
            return {"success": False, "message": "No active employment to terminate"}

        end_date_raw = request_data.get("end_date")
        term_date = datetime.utcnow().date()
        if end_date_raw:
            try:
                term_date = datetime.fromisoformat(end_date_raw).date()
            except ValueError:
                pass

        employment.status = "terminated"
        employment.end_date = term_date
        if request_data.get("notes"):
            employment.notes = request_data["notes"]
        employment.updated_by_id = executor.id
        person.is_active = False
        log_action(
            action="people.terminated",
            actor=executor,
            target_type="person",
            target_id=person.id,
            target_label=person.full_name,
            details={"end_date": term_date.isoformat()},
        )
        return {"success": True, "message": f"Terminated: {person.full_name}"}

    elif action == "people.convert_intern":
        from app.models import Person, Employment
        from datetime import date

        person = Person.query.get(target_id)
        if not person:
            return {"success": False, "message": "Person not found"}
        current = person.active_employment
        if not current or current.employment_type != "intern":
            return {"success": False, "message": "Person is not an active intern"}

        current.status = "completed"
        current.end_date = date.today()

        start_date = date.today()
        if request_data.get("start_date"):
            try:
                start_date = datetime.fromisoformat(request_data["start_date"]).date()
            except ValueError:
                pass

        new_employment = Employment(
            person_id=person.id,
            employment_type="full_time",
            intern_track=None,
            status="active",
            title=request_data.get("title") or current.title,
            start_date=start_date,
            manager_person_id=request_data.get("manager_person_id", current.manager_person_id),
            mentor_person_id=None,
            created_by_id=executor.id,
        )
        db.session.add(new_employment)
        log_action(
            action="people.converted_to_full_time",
            actor=executor,
            target_type="person",
            target_id=person.id,
            target_label=person.full_name,
            details={"from_track": current.intern_track, "new_title": new_employment.title},
        )
        return {"success": True, "message": f"Converted intern to full-time: {person.full_name}"}

    elif action == "people.export_bulk":
        return {"success": True, "message": "Bulk export approved; requester may now download with approval_request_id"}

    elif action == "people.issue_certificate":
        from app.models import Person
        from app.routes.internship import _issue_certificate

        person = Person.query.get(target_id)
        if not person:
            return {"success": False, "message": "Person not found"}

        certificate = _issue_certificate(
            person=person,
            actor=executor,
            pdf_url=request_data.get("pdf_url"),
        )
        return {
            "success": True,
            "message": f"Issued certificate for {person.full_name}",
            "certificate_id": certificate.id,
            "certificate_no": certificate.certificate_no,
        }

    elif action == "people.finalize_milestone":
        from app.models import MilestoneReview
        from app.routes.internship import _finalize_milestone

        milestone = MilestoneReview.query.get(request_data.get("milestone_id") or target_id)
        if not milestone:
            return {"success": False, "message": "Milestone review not found"}
        if milestone.status == "released":
            return {"success": False, "message": "Milestone review already finalized"}

        decision = request_data.get("decision")
        if decision not in {"convert", "extend", "reassign", "release"}:
            return {"success": False, "message": f"Invalid decision: {decision}"}

        _finalize_milestone(milestone, decision, executor)
        return {
            "success": True,
            "message": f"Finalized {milestone.review_type} review for {milestone.person.full_name}: {decision}",
        }

    elif action == "people.finalize_employee_review":
        from app.models import EmployeeReview
        from app.routes.performance import _apply_employee_decision

        review = EmployeeReview.query.get(request_data.get("review_id") or target_id)
        if not review:
            return {"success": False, "message": "Employee review not found"}
        if review.status == "completed":
            return {"success": False, "message": "Employee review already finalized"}

        decision = request_data.get("decision")
        if decision not in {"retain", "extend", "promote", "terminate"}:
            return {"success": False, "message": f"Invalid decision: {decision}"}

        review.score = request_data.get("score", review.score)
        _apply_employee_decision(review, decision, request_data.get("new_title"), executor)
        return {
            "success": True,
            "message": f"Finalized {review.quarter} review for {review.person.full_name}: {decision}",
        }

    elif action == "secret.reveal":
        return {"success": True, "message": "Secret reveal approved"}

    elif action in {"agent.export", "agent.write_external"}:
        if approval.target_type == "generated_artifact":
            from app.models import GeneratedArtifact, ExternalDestination
            from app.services.agent_service import publish_generated_artifact

            artifact_id = request_data.get("artifact_id") or target_id
            artifact = GeneratedArtifact.query.get(artifact_id)
            if not artifact:
                return {"success": False, "message": "Generated artifact not found"}

            if action == "agent.export":
                return {"success": True, "message": f"Approved artifact export {artifact_id}"}

            destination_id = request_data.get("destination_id")
            if not destination_id:
                return {"success": False, "message": "Missing destination_id"}

            destination = ExternalDestination.query.filter_by(id=destination_id, is_active=True).first()
            if not destination:
                return {"success": False, "message": "Destination not found or inactive"}

            mode = request_data.get("mode", "overwrite")
            result = publish_generated_artifact(artifact, destination, actor=executor, mode=mode)
            return {
                "success": True,
                "message": f"Published artifact {artifact_id}",
                "result": result,
            }

        from app.models import AgentRequest
        from app.services.agent_service import process_agent_request

        agent_request_id = request_data.get("agent_request_id") or target_id
        if not agent_request_id:
            return {"success": False, "message": "Missing agent_request_id"}

        agent_request = AgentRequest.query.get(agent_request_id)
        if not agent_request:
            return {"success": False, "message": "Agent request not found"}

        result = process_agent_request(agent_request, executor)
        artifact = result.get("artifact") or {}
        return {
            "success": True,
            "message": f"Executed agent request {agent_request_id}",
            "artifact_id": artifact.get("id"),
        }

    return {"success": False, "message": f"Unknown action: {action}"}


# Available protected actions for reference
PROTECTED_ACTIONS = [
    "upload.delete",
    "user.role_change", 
    "user.disable",
    "job.cancel",
    "people.terminate",
    "people.convert_intern",
    "people.export_bulk",
    "people.issue_certificate",
    "people.finalize_milestone",
    "people.finalize_employee_review",
    "secret.reveal",
    "agent.export",
    "agent.write_external",
]


@governance_bp.get("/policies/actions")
@require_role("admin")
def list_available_actions():
    """List all available protected actions."""
    return jsonify(PROTECTED_ACTIONS)
