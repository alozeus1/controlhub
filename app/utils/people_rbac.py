from typing import Optional, Tuple

from app.models import Person


def get_person_for_user(user_id: int) -> Optional[Person]:
    return Person.query.filter_by(user_id=user_id).first()


def is_hr_admin(actor) -> bool:
    return actor.role in {"superadmin", "hr_admin"}


def can_manage_person(actor, person: Person) -> Tuple[bool, str]:
    """
    Managers can update direct reports only.
    HR admins/superadmins can update all people.
    """
    if is_hr_admin(actor) or actor.role == "admin":
        return True, ""

    actor_person = get_person_for_user(actor.id)
    if not actor_person:
        return False, "No linked person profile for actor"

    employment = person.active_employment
    if actor.role == "people_manager":
        if employment and employment.manager_person_id == actor_person.id:
            return True, ""
        return False, "people_manager can only update direct reports"

    return False, "Insufficient permissions to manage this person"


def is_poc_for(actor, person: Person) -> bool:
    """True when the actor is the assigned PoC/team lead on the person's
    active employment."""
    actor_person = get_person_for_user(actor.id)
    if not actor_person:
        return False
    employment = person.active_employment
    return bool(employment and employment.poc_person_id == actor_person.id)


def can_add_checkin(actor, person: Person) -> Tuple[bool, str]:
    """
    Mentors can add check-ins for interns they mentor.
    Managers/HR/admin can add check-ins for managed people.
    """
    if is_hr_admin(actor) or actor.role in {"admin", "people_manager"}:
        return can_manage_person(actor, person)

    if actor.role != "mentor":
        return False, "Only mentors/managers/HR can add check-ins"

    actor_person = get_person_for_user(actor.id)
    if not actor_person:
        return False, "No linked person profile for actor"

    employment = person.active_employment
    if not employment:
        return False, "Person has no active employment"
    if employment.employment_type != "intern":
        return False, "Mentors can only add check-ins for interns"
    if employment.mentor_person_id != actor_person.id:
        return False, "mentor can only add check-ins for assigned interns"
    return True, ""

