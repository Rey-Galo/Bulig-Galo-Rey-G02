"""Case workflow rules (SDD BR-02/03, BR-07, BR-10-13, BR-16-18). Views call these; every rule is checked here."""

import secrets
from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from schools.models import School, SchoolMembership

from .models import CaseAcknowledgement, CaseRecord, Report, Severity, TriageReview

Status = CaseRecord.Status
Role = SchoolMembership.Role

# BR-17: allowed staff transitions after acknowledgement. Closed cases never reopen.
NEXT_STATUSES = {
    Status.ACKNOWLEDGED: {Status.IN_PROGRESS, Status.CLOSED},
    Status.IN_PROGRESS: {Status.REFERRED, Status.CLOSED},
    Status.REFERRED: {Status.CLOSED},
}


def active_recipients(school: School) -> QuerySet[SchoolMembership]:
    return school.memberships.filter(is_active=True, is_trusted_recipient=True, account__is_active=True).select_related(
        'account'
    )


def schools_accepting_reports() -> QuerySet[School]:
    """BR-08: only active schools with at least one active trusted recipient take intake."""
    return School.objects.filter(
        is_active=True,
        memberships__is_active=True,
        memberships__is_trusted_recipient=True,
        memberships__account__is_active=True,
    ).distinct()


@transaction.atomic
def submit_report(*, intake_request_id, school: School, recipient: SchoolMembership, **fields) -> tuple[Report, bool]:
    """Create the report and its pending case together. Returns (report, created).

    BR-03: a retry with the same request id returns the existing report; a changed payload is rejected.
    """
    existing = Report.objects.filter(intake_request_id=intake_request_id).first()
    if existing:
        same = (
            existing.school_id == school.pk
            and existing.recipient_membership_id == recipient.pk
            and existing.original_text == fields['original_text']
        )
        if not same:
            raise ValidationError('This form was already submitted. Reload the page to send a new report.')
        return existing, False
    if recipient.school_id != school.pk or not active_recipients(school).filter(pk=recipient.pk).exists():
        raise ValidationError('That adult is not available for this school.')
    report = Report.objects.create(
        intake_request_id=intake_request_id, school=school, recipient_membership=recipient, **fields
    )
    CaseRecord.objects.create(report=report, case_number=_new_case_number(school), owner_membership=recipient)
    return report, True


def _new_case_number(school: School) -> str:
    # 8 hex chars per school prefix; a clash would fail the unique constraint, not overwrite anything.
    return f'{school.school_code}-{secrets.token_hex(4).upper()}'


def visible_cases(account) -> QuerySet[CaseRecord]:
    """BR-07: current owner, original recipient, or an active head of the report's school."""
    mine = SchoolMembership.objects.filter(account=account, is_active=True)
    head_schools = mine.filter(role=Role.SCHOOL_HEAD).values('school')
    return (
        CaseRecord.objects.filter(report__school__in=mine.values('school'))
        .filter(
            Q(owner_membership__in=mine)
            | Q(report__recipient_membership__in=mine)
            | Q(report__school__in=head_schools)
        )
        .select_related('report__school', 'owner_membership__account', 'report__recipient_membership__account')
    )


def acting_membership(account, case: CaseRecord) -> SchoolMembership | None:
    """The account's active membership in the case's school, if it may change the case (owner or head)."""
    membership = SchoolMembership.objects.filter(account=account, school_id=case.report.school_id, is_active=True).first()
    if membership and (membership.pk == case.owner_membership_id or membership.role == Role.SCHOOL_HEAD):
        return membership
    return None


def _lock(case: CaseRecord, actor) -> tuple[CaseRecord, SchoolMembership]:
    locked = CaseRecord.objects.select_for_update().select_related('report__school').get(pk=case.pk)
    membership = acting_membership(actor, locked)
    if membership is None:
        raise PermissionDenied
    return locked, membership


@transaction.atomic
def review_case(case: CaseRecord, actor, *, severity: str, reason: str) -> CaseRecord:
    """BR-10/12/13: the one human review. Moves PENDING_REVIEW to OPEN and starts the acknowledgement clock."""
    case, membership = _lock(case, actor)
    if case.status != Status.PENDING_REVIEW:
        raise ValidationError('This case has already been reviewed.')
    now = timezone.now()
    school = case.report.school
    minutes = {
        Severity.HIGH: school.high_ack_minutes,
        Severity.MODERATE: school.moderate_ack_minutes,
        Severity.LOW: school.low_ack_minutes,
    }[severity]
    TriageReview.objects.create(
        case=case, reviewer_membership=membership, confirmed_severity=severity, reason=reason, reviewed_at=now
    )
    case.status = Status.OPEN
    case.confirmed_severity = severity
    case.reviewed_at = now
    case.initial_ack_minutes = minutes
    case.ack_due_at = now + timedelta(minutes=minutes)
    case.save()
    return case


@transaction.atomic
def acknowledge_case(case: CaseRecord, actor) -> CaseRecord:
    """BR-16: only an OPEN case, only once."""
    case, membership = _lock(case, actor)
    if case.status != Status.OPEN:
        raise ValidationError('Only an open, reviewed case can be acknowledged.')
    CaseAcknowledgement.objects.create(case=case, actor_membership=membership, acknowledged_at=timezone.now())
    case.status = Status.ACKNOWLEDGED
    case.save(update_fields=['status'])
    return case


@transaction.atomic
def change_status(case: CaseRecord, actor, *, status: str, referral_destination: str = '', resolution_summary: str = '') -> CaseRecord:
    """BR-17: allowed transitions only; referral needs a destination, closing needs a resolution."""
    case, _ = _lock(case, actor)
    if status not in NEXT_STATUSES.get(case.status, set()):
        raise ValidationError(f'A {case.get_status_display().lower()} case cannot move to that status.')
    if status == Status.REFERRED:
        if not referral_destination.strip():
            raise ValidationError('Say where the case was referred to.')
        case.referral_destination = referral_destination.strip()
    if status == Status.CLOSED:
        if not resolution_summary.strip():
            raise ValidationError('Write a short resolution before closing the case.')
        case.resolution_summary = resolution_summary.strip()
        case.closed_at = timezone.now()
    case.status = status
    case.save()
    return case


@transaction.atomic
def reassign_case(case: CaseRecord, actor, *, new_owner: SchoolMembership) -> CaseRecord:
    """BR-18: school heads only, to an active membership in the same school; the original recipient is kept."""
    case, membership = _lock(case, actor)
    if membership.role != Role.SCHOOL_HEAD:
        raise PermissionDenied
    if case.status == Status.CLOSED:
        raise ValidationError('Closed cases cannot be reassigned.')
    if new_owner.school_id != case.report.school_id or not new_owner.is_active:
        raise ValidationError('Pick an active staff member from this school.')
    case.owner_membership = new_owner
    case.save(update_fields=['owner_membership'])
    return case
