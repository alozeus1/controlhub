# Employee Quarterly Reviews & PoC Workspace — Design

Approved by product owner (chat, 2026-07-08). Companion to the intern PoC
workflow shipped earlier the same day.

## Problem

ControlHub reviews only interns. PoCs/team leads and regular employees have no
performance workflow of their own, PoCs cannot see the full intern roster, and
there is no central place to assign interns to PoCs.

## Model (two tracks, split by employment_type)

1. **Interns** (`employment_type == "intern"`): unchanged — onboarding,
   biweekly (intern → PoC → manager), 3/6-month milestones,
   convert/extend/reassign/release.
2. **Employees** (everything else, including PoCs/team leads): new
   **quarterly performance review**. Employees are assigned a Manager only —
   never a PoC. PoCs are employees here: they self-report up to their manager
   while separately assessing their interns.

## Quarterly review lifecycle

- **Company-aligned calendar quarters** (Q1 Jan–Mar … Q4 Oct–Dec). Every
  active non-intern employee gets exactly one review per quarter regardless of
  start date. Unique constraint `(person_id, quarter)` (e.g. `2026-Q3`).
- **Idempotent auto-creation** (`ensure_quarterly_reviews`): creates the
  current quarter's review (`pending_self`) for any active employee missing
  one. Runs lazily when the ops dashboard or an employee's workspace loads,
  and via `POST /admin/performance/reviews/ensure` (admin/manager; later a
  Render cron target). No background worker.
- **States**: `pending_self` → employee submits self-report → `pending_manager`
  → manager scores (1–5), strengths, concerns, action items, decision →
  `completed`.
- **Decisions**: `retain` (no-op), `extend` (+90 days on end_date), `promote`
  (requires `new_title`; updates employment title), `terminate` (status
  completed + end date today). `terminate` routes through the governance
  approval queue when a policy on `people.finalize_employee_review` is active
  (mirrors intern milestone gating).
- Draft AI summary generated at completion; human decision is authoritative.

## RBAC

- Employee reviews visible to: the employee (own), their manager, HR/admin.
- Managers grade only their reports (`can_manage_person`); PoCs cannot open,
  grade, or decide employee reviews.
- **PoC roster visibility widened**: `team_lead` can browse the People list
  (read-only reach; backend edit scoping unchanged — they still only assess
  their own assigned interns).

## Surfaces

- **My Journey**: employees (incl. PoCs) see "My Quarterly Reviews" — pending
  self-report form, history with scores/feedback/decisions. Interns unchanged.
- **PersonDetail**: "Quarterly Reviews" card on non-intern profiles — manager
  grades and decides there (modal mirrors the biweekly grading form plus the
  decision select and conditional new-title field).
- **Team Ops** (renamed from Intern Ops; same `/ui/intern-ops` route): adds an
  Employee Reviews panel (awaiting self-report / awaiting manager) scoped like
  the intern sections.
- **Team Lead Assignments** (`/ui/team-assignments`, admin/manager): roster of
  every team lead with their assigned interns; reassign/unassign inline; lists
  unassigned interns. The per-profile PoC dropdown remains.

## Components

- `EmployeeReview` model + migration `p6q7r8s9t0u1`.
- New blueprint `app/routes/performance.py` (list / ensure / self-submit /
  manager-submit), registered under `/admin`.
- Governance executor for `people.finalize_employee_review`.
- Seed: Tessa (PoC) and Marcus get employee Employment rows (Tessa managed by
  Marcus) so quarterly reviews auto-generate in demo.
- Tests: `tests/test_saas_employee_reviews.py` — idempotent ensure (skips
  interns, one per quarter), self-submit own-only, manager scoping, each
  decision's side effect, terminate approval gating, PoC blocked from grading.

## Out of scope (Phase 3 backlog)

Notifications, manager sub-types, wiki, review calendar; PoC roster page
filters beyond basics.
