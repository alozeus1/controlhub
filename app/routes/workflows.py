from flask import Blueprint, request, jsonify
from app.extensions import db
from app.models import WorkflowTemplate, WorkflowTemplateStep, WorkflowRun, WorkflowRunStep
from app.utils.rbac import require_role, require_active_user
from datetime import datetime

workflows_bp = Blueprint("workflows", __name__)

@workflows_bp.get("/workflows/templates")
@require_active_user
def list_templates():
    templates = WorkflowTemplate.query.filter_by(is_active=True).order_by(WorkflowTemplate.name).all()
    return jsonify({"items": [t.to_dict() for t in templates], "total": len(templates)})

@workflows_bp.post("/workflows/templates")
@require_role("admin")
def create_template():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("workflow_type"):
        return jsonify({"error": "name and workflow_type are required"}), 400
    t = WorkflowTemplate(name=data["name"], workflow_type=data["workflow_type"],
                         description=data.get("description"),
                         created_by_id=request.current_user.id)
    db.session.add(t)
    db.session.flush()
    for i, step_data in enumerate(data.get("steps", [])):
        step = WorkflowTemplateStep(template_id=t.id, order=i+1,
                                    title=step_data["title"],
                                    description=step_data.get("description"),
                                    assignee_role=step_data.get("assignee_role"))
        db.session.add(step)
    db.session.commit()
    t_dict = t.to_dict()
    t_dict["steps"] = [s.to_dict() for s in sorted(t.steps, key=lambda x: x.order)]
    return jsonify(t_dict), 201

@workflows_bp.get("/workflows/templates/<int:template_id>")
@require_active_user
def get_template(template_id):
    t = WorkflowTemplate.query.get_or_404(template_id)
    d = t.to_dict()
    d["steps"] = [s.to_dict() for s in sorted(t.steps, key=lambda x: x.order)]
    return jsonify(d)

@workflows_bp.delete("/workflows/templates/<int:template_id>")
@require_role("admin")
def delete_template(template_id):
    t = WorkflowTemplate.query.get_or_404(template_id)
    t.is_active = False
    db.session.commit()
    return jsonify({"message": "Deactivated"})

@workflows_bp.get("/workflows/runs")
@require_active_user
def list_runs():
    status = request.args.get("status")
    q = WorkflowRun.query
    if status:
        q = q.filter_by(status=status)
    runs = q.order_by(WorkflowRun.created_at.desc()).limit(50).all()
    return jsonify({"items": [r.to_dict() for r in runs], "total": len(runs)})

@workflows_bp.post("/workflows/runs")
@require_active_user
def start_run():
    data = request.get_json() or {}
    if not data.get("template_id"):
        return jsonify({"error": "template_id is required"}), 400
    template = WorkflowTemplate.query.get_or_404(data["template_id"])
    run = WorkflowRun(template_id=template.id,
                      subject_user_id=data.get("subject_user_id"),
                      subject_name=data.get("subject_name"),
                      started_by_id=request.current_user.id)
    db.session.add(run)
    db.session.flush()
    for step in sorted(template.steps, key=lambda s: s.order):
        rs = WorkflowRunStep(run_id=run.id, template_step_id=step.id,
                             order=step.order, title=step.title,
                             description=step.description)
        db.session.add(rs)
    db.session.commit()
    d = run.to_dict()
    d["steps"] = [s.to_dict() for s in sorted(run.run_steps, key=lambda x: x.order)]
    return jsonify(d), 201

@workflows_bp.get("/workflows/runs/<int:run_id>")
@require_active_user
def get_run(run_id):
    run = WorkflowRun.query.get_or_404(run_id)
    d = run.to_dict()
    d["steps"] = [s.to_dict() for s in sorted(run.run_steps, key=lambda x: x.order)]
    return jsonify(d)

@workflows_bp.patch("/workflows/runs/<int:run_id>/steps/<int:step_id>")
@require_active_user
def update_step(run_id, step_id):
    step = WorkflowRunStep.query.filter_by(id=step_id, run_id=run_id).first_or_404()
    data = request.get_json() or {}
    new_status = data.get("status")
    if new_status:
        step.status = new_status
        if new_status == "completed":
            step.completed_by_id = request.current_user.id
            step.completed_at = datetime.utcnow()
    if "notes" in data:
        step.notes = data["notes"]
    db.session.commit()
    # Check if all steps done
    run = step.run
    all_done = all(s.status in ("completed","skipped") for s in run.run_steps)
    if all_done and run.status == "active":
        run.status = "completed"
        run.completed_at = datetime.utcnow()
        db.session.commit()
    return jsonify(step.to_dict())
