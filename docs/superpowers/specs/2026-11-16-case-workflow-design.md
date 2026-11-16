# PD2 core feature: anonymous intake + case workflow

Date: 2026-11-16. Deadline: 21:30 same day.

## Goal

One vertical slice of Bulig's core job: a student submits an anonymous report to a
trusted adult, and that adult (or the school head) carries the case from pending review
to closed. Everything is stored in Supabase Postgres and driven through Django templates.

## In scope

New app `cases`. Models (names and tables follow the SDD):

| Model | Key fields | Notes |
|---|---|---|
| `School` (`school`) | division FK, school_code UQ, name, is_active, high/moderate/low_ack_minutes (>0) | No `head_membership_id`; "school head" = any active `SCHOOL_HEAD` membership. |
| `SchoolMembership` (`school_membership`) | school FK, account FK, role (TEACHER/GUIDANCE/SCHOOL_HEAD), is_trusted_recipient, is_active | UQ(school, account). STAFF accounts only. |
| `Report` (`report`) | intake_request_id UQ, school FK, recipient_membership FK, original_text, language_code, category?, submitted_at | Immutable. No student identity, no IP. |
| `CaseRecord` (`case_record`) | report 1:1, case_number UQ, owner_membership FK, status, confirmed_severity?, initial_ack_minutes?, ack_due_at?, opened_at, reviewed_at?, referral_destination, resolution_summary, closed_at? | DB checks for pending/closed consistency. |
| `TriageReview` (`triage_review`) | case 1:1, reviewer_membership FK, decision (MANUAL), confirmed_severity, reason, reviewed_at | One final review per case. |
| `CaseAcknowledgement` (`case_acknowledgement`) | case PK/FK, actor_membership FK, acknowledged_at | At most one per case. |

All FKs are `RESTRICT`. UUID PKs.

### Flows

1. **Intake (public, no login).** Step 1: pick an active school. Step 2: pick an active
   opted-in recipient of that school, language, optional category, and 20–5000 chars of text.
   A hidden server-made `intake_request_id` makes retries idempotent (BR-03). Report and
   pending case are created in one transaction. The receipt page shows the
   immediate-danger notice and no case data.
2. **Case queue (STAFF, login).** Shows cases the user may see (BR-07): current owner,
   original recipient, or an active school head of that school. Filter by status and severity.
3. **Case detail and actions.** Mutations are allowed only for the owner or a same-school head:
   - Review (PENDING_REVIEW → OPEN): severity + reason. Snapshots the school's window and sets `ack_due_at`.
   - Acknowledge (OPEN → ACKNOWLEDGED).
   - Start (ACKNOWLEDGED → IN_PROGRESS), refer (IN_PROGRESS → REFERRED, destination required), and
     close (ACKNOWLEDGED/IN_PROGRESS/REFERRED → CLOSED, resolution required). Closed cases stay closed.
   - Reassign (head only, to an active membership in the same school).
4. **Membership CRUD (STAFF).** Join a school as TEACHER or GUIDANCE (create), list mine (read),
   toggle trusted-recipient opt-in (update), and leave (delete). Leaving is blocked while the user
   still owns a non-closed case (BR-26). SCHOOL_HEAD is granted only through Django admin.
5. **Dashboards.**
   - Staff: case counts by status and links to the queue and memberships.
   - Division admin: per-school aggregate counts for their own division only, with no case data (BR-22).
   - Platform admin: school count only.

### Validation and messages

Form errors use `BootstrapMixin`. Every state change is re-checked on the server, and an
illegal transition returns a flash error. Wrong-school access returns 404.

### Seed

The `seed_demo` management command creates a demo division, a school, and the test accounts
(head, teacher, division admin) for the completion report.

## Out of scope (listed as remaining tasks)

AI drafts (F-04), follow-up code and messaging (F-03), escalation worker and timers beyond
`ack_due_at` (F-07), notifications and audit log (F-08), encryption at rest (BR-27), and a
designated head FK.

## Git plan (user runs commands)

`develop` from `main` → `feature/school-membership` (School, Membership, CRUD, admin, seed)
→ PR into develop → `feature/case-workflow` (Report, Case, intake, queue, actions, dashboards)
→ PR into develop → PR from develop into main.
