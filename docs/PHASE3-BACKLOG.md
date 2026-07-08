# Phase 3 Backlog

Feature requests and improvements captured from the first internal UAT round
(July 2026). Ordered by suggested priority. Items in Phase 2.5 were fixed
immediately after UAT (see git history): validation errors now show details in
toasts, timestamps render in the viewer's local timezone, draft-recommendation
approval can be revoked while a review is a draft, and the onboarding radar
only counts templates targeting the person's role.

## 1. Notification system (high)
- In-app notification bell for admins, managers, and interns.
- Notify on every action pertaining to the user's own profile/queue:
  review opened, reflection submitted, review graded, milestone compiled,
  decision released, onboarding item overdue, approval requested/decided.
- Notifications clear when addressed, or can be dismissed manually.
- Per-user toggle in Settings to enable/disable notification alerts.
- Note: a `notification` model/channel system already exists in the backend
  (FEATURE_NOTIFICATIONS); wire the internship events into it rather than
  building a parallel system, and add a per-user preferences table.

## 2. Manager role types with scoped permissions (high)
- Split `people_manager` into three manager archetypes:
  - **Product Manager** — program/cohort/template administration.
  - **People Manager** — reviews, onboarding, milestone decisions for reports.
  - **Operations Manager** — analytics, exports, compliance views.
- COO-style role sees/does everything both PM and People Manager can.
- Superadmin gets a "role designer" tab (command-center) to toggle which
  features/pages each manager type can access.
- Implementation note: extend ROLE_LEVELS with capability flags rather than
  pure hierarchy; sidebar + require_role checks read from a capability map.

## 3. In-app wiki / documentation hub (high)
- A documentation page teaching new users how to operate ControlHub:
  what each page does, what can be changed, what to watch out for when
  filing or updating — one track for admins, one for regular users (RBAC-aware:
  show only the docs for pages the viewer can access).
- Make the same content available to the AI Manager Assistant chatbot so it
  can answer "how do I…" questions about operating ControlHub.
- Start from docs/ + README content; render with the existing Markdown
  component (see DocPage.css / Privacy & Support pages for the pattern).

## 4. Intern onboarding tab under My Journey (medium)
- Move the onboarding checklist to its own tab within My Journey.
- Per-item notes: what exactly is expected, and who to contact for help.
- Link each item to the relevant onboarding documentation (ties into #3).
- Data model: add `notes`/`help_contact`/`doc_url` columns to
  OnboardingTemplateItem.

## 5. Program & cohort form UX (medium)
- Cohort form: program picker should more clearly require a selection, and
  offer an inline "+ New program…" option that expands the program creation
  fields, instead of requiring a separate step.
- Clearly mark required fields (name, track) before submit.

## 6. Policy lifecycle UI (medium)
- Deactivated policies currently disappear from action: add explicit
  Reactivate and Delete controls, and show inactive policies in a filterable
  list. (Backend supports is_active toggling; this is UI work.)

## 7. Timezone preference (low)
- Timestamps now render in the browser's local timezone automatically.
- Optional follow-up: an explicit timezone picker in Settings for users who
  want to view logs in a fixed zone (e.g. team standard CST) regardless of
  their device timezone.

## 8. Review calendar & reminders (low, pairs with #1)
- Calendar view of biweekly periods and milestone due dates.
- Scheduled overdue reminders through the notification system and the
  Mattermost/email integrations (senders already exist, env-gated).
