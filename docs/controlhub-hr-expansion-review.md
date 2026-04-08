# Control Hub HR / Internship Expansion - Discovery Review

This document serves as the architecture review and discovery note prior to implementing the requested HR / Internship expansion, Manager Demo, and Landing Page Welcome Video for Control Hub.

## Target Goals & Outcomes
The platform needs to extend its workforce management for employees and interns without breaking existing flows. It requires deep-links across personas, modern tabs, cohort tracking, analytics, an instructional manager demo, and a Remotion welcome video.

## Current Setup Overview

### Models and Relationships
- `Person`: Identity, contact, team, department, cohort (free text currently).
- `Employment`: Links to Person. Tracks contract start/end, salary, managers, and status. It has most of the compensation tracking the prompt refers to (`compensation_type`, `salary_amount`, `contract_signed_date`, etc.).
- `InternshipProgram`: overarching internship.
- `InternshipCohort`: ties to Program, contains `track` and `department`.
- `InternshipCohortMember`: Link table between Person and Cohort, tracking role (intern/manager etc).
- `Onboarding` / `Checkin` models: Exist for tracking tasks and evaluations.

**What is missing:**
- `contract_status`, `offer_letter_url`, `contract_document_url` in `Employment`.
- `graduation_status` in `InternshipCohortMember`.
- Strict taxonomy enums for Department/Specializations.

### Routes and Handlers
- `/internship/programs`, `/internship/cohorts`, `/internship/cohorts/<id>/members` provide standard CRUD.
- `/people` provides workforce personnel listing and employment history creation.
- `app/routes/agent_service.py` manages asynchronous and synchronous "Export" style AI generations from DB queries.

**What is missing:**
- `/admin/internship/cohort-analysis` summarizing statistics.
- Strict payload validations for the new controlled taxonomy in `/people`.

### UI Screens and Navigation
- `admin-ui/src/pages/People.jsx`: Basic list formatting, lacking depth for HR profiles and multi-dimensional filters.
- `admin-ui/src/pages/InternshipProgram.jsx`: Functional forms and tables but somewhat flat; it needs an upgrade to a cohesive tabbed interface representing Overview, Cohorts, Performance, Check-ins, and Analytics using `Recharts`.

### AI Copilot Capability
- Currently utilizes predefined queries via `query_module_rows` with `AgentRequest` logging. It is built strictly for exporting and reading (which is safe), but with prompt injection the user wants to ask "natural language questions". An upgrade here might include injecting the DB schema into a QA chain or writing a specific `Workforce` module scope that handles NL queries.

## Risk Analysis vs Outcomes

- **Risk: Breaking existing People API if we just enforce enums suddenly.**
  - *Mitigation*: The backend will need to accept current existing free-text on legacy users until they are updated, but enforce the new taxonomy (`Software Development`, `DevOps`) on new saves. The migration should not wipe out old data.
  
- **Risk: Remotion Video API keys**
  - *Mitigation*: Implement `.env` checking, defaulting to a visual-only render if the ElevenLabs voiceover fails or the key is absent to avoid pipeline breaks.

- **Risk: Agent Service writes**
  - *Mitigation*: The prompt explicitly states "explicit human confirmation for write actions affecting pay/contracts/status". Given the current AI setup is primarily module-query based, building "Write Tools" for the AI might be a stretch goal that strictly requires `ApprovalRequest` usage which is currently available in the app logic. We will ensure any mutate tools require approvals.

## Implementation Map

1. `app/models.py`: Inject new DB Columns. Create Enums for Taxonomy.
2. `app/routes/internship.py`: Add the Cohort Analysis SQL grouping endpoints.
3. `admin-ui/src/pages/InternshipProgram.jsx`: Overhaul to Tabs and plug in Recharts for the analysis endpoint.
4. `admin-ui/src/pages/People.jsx`: Expand filters and display forms for new contract fields.
5. Create `remotion/` project scaffold for Welcome Video execution.
6. Build Demo scripts & internal docs in `docs/` dir.
