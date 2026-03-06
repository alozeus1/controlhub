"""Export template registry backed by database records."""

from app.extensions import db
from app.models import ExportTemplate


DEFAULT_TEMPLATES = [
    {
        "id": "employee_directory",
        "name": "Employee Directory",
        "module_scope": "people",
        "description": "Directory of active employees and staff records",
        "allowed_fields": [
            "person_id",
            "full_name",
            "email",
            "phone",
            "team",
            "department",
            "cohort",
            "employment_type",
            "intern_track",
            "employment_status",
            "title",
            "manager_name",
            "mentor_name",
            "start_date",
            "end_date",
        ],
        "masking_rules": {"phone": "partial"},
        "classification": "internal",
        "pii_flag": True,
        "is_active": True,
    },
    {
        "id": "intern_roster_by_track",
        "name": "Intern Roster by Track",
        "module_scope": "people",
        "description": "Intern cohort report segmented by track and manager/mentor",
        "allowed_fields": [
            "person_id",
            "full_name",
            "email",
            "team",
            "department",
            "cohort",
            "intern_track",
            "employment_status",
            "title",
            "manager_name",
            "mentor_name",
            "start_date",
            "end_date",
        ],
        "masking_rules": {},
        "classification": "internal",
        "pii_flag": True,
        "is_active": True,
    },
]


def ensure_default_templates():
    changed = False
    for template_data in DEFAULT_TEMPLATES:
        existing = ExportTemplate.query.get(template_data["id"])
        if existing:
            continue
        db.session.add(ExportTemplate(**template_data))
        changed = True

    if changed:
        db.session.commit()


def get_template(template_id, module_scope=None):
    ensure_default_templates()
    query = ExportTemplate.query.filter_by(id=template_id, is_active=True)
    if module_scope:
        query = query.filter_by(module_scope=module_scope)
    return query.first()


def list_templates(module_scope=None):
    ensure_default_templates()
    query = ExportTemplate.query.filter_by(is_active=True)
    if module_scope:
        query = query.filter_by(module_scope=module_scope)
    return [template.to_dict() for template in query.order_by(ExportTemplate.name.asc()).all()]
