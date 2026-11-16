import uuid

from django.db import models
from django.db.models import Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import GreaterThanOrEqual, LessThanOrEqual

from schools.models import SchoolMembership


class Severity(models.TextChoices):
    HIGH = 'HIGH', 'High'
    MODERATE = 'MODERATE', 'Moderate'
    LOW = 'LOW', 'Low'


class Report(models.Model):
    """Anonymous intake. Immutable after it is accepted (SDD 4.4.5). No student identity is stored."""

    class Language(models.TextChoices):
        CEBUANO = 'ceb', 'Bisaya'
        TAGALOG = 'tl', 'Tagalog'
        ENGLISH = 'en', 'English'

    class Category(models.TextChoices):
        BULLYING = 'BULLYING', 'Bullying'
        THREAT = 'THREAT', 'Threat'
        HOME_ABUSE = 'HOME_ABUSE', 'Problem at home'
        MENTAL_HEALTH = 'MENTAL_HEALTH', 'Mental health'
        OTHER = 'OTHER', 'Something else'

    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    intake_request_id = models.UUIDField(unique=True)
    school = models.ForeignKey('schools.School', on_delete=models.RESTRICT, db_column='school_id', related_name='reports')
    recipient_membership = models.ForeignKey(
        SchoolMembership, on_delete=models.RESTRICT, db_column='recipient_membership_id', related_name='received_reports'
    )
    original_text = models.TextField()
    language_code = models.CharField(max_length=3, choices=Language.choices)
    category = models.CharField(max_length=20, choices=Category.choices, null=True, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'report'
        constraints = [
            # BR-02: 20-5000 characters, not counting leading/trailing whitespace for the minimum.
            models.CheckConstraint(condition=GreaterThanOrEqual(Length(Trim('original_text')), 20), name='report_text_min'),
            models.CheckConstraint(condition=LessThanOrEqual(Length('original_text'), 5000), name='report_text_max'),
        ]

    def __str__(self) -> str:
        return f'Report {self.pk}'


class CaseRecord(models.Model):
    """Workflow state for one report (SDD 4.4.7)."""

    class Status(models.TextChoices):
        PENDING_REVIEW = 'PENDING_REVIEW', 'Pending review'
        OPEN = 'OPEN', 'Open'
        ACKNOWLEDGED = 'ACKNOWLEDGED', 'Acknowledged'
        IN_PROGRESS = 'IN_PROGRESS', 'In progress'
        REFERRED = 'REFERRED', 'Referred'
        CLOSED = 'CLOSED', 'Closed'

    case_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.OneToOneField(Report, on_delete=models.RESTRICT, db_column='report_id', related_name='case')
    case_number = models.CharField(max_length=30, unique=True)
    owner_membership = models.ForeignKey(
        SchoolMembership, on_delete=models.RESTRICT, db_column='owner_membership_id', related_name='owned_cases'
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING_REVIEW)
    confirmed_severity = models.CharField(max_length=8, choices=Severity.choices, null=True, blank=True)
    initial_ack_minutes = models.IntegerField(null=True, blank=True)
    ack_due_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    referral_destination = models.CharField(max_length=200, blank=True)
    resolution_summary = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'case_record'
        ordering = ['-opened_at']
        constraints = [
            # Pending cases have no human severity or clock; every other state has all of them.
            models.CheckConstraint(
                condition=(
                    Q(
                        status='PENDING_REVIEW',
                        confirmed_severity__isnull=True,
                        reviewed_at__isnull=True,
                        initial_ack_minutes__isnull=True,
                        ack_due_at__isnull=True,
                    )
                    | (
                        ~Q(status='PENDING_REVIEW')
                        & Q(
                            confirmed_severity__isnull=False,
                            reviewed_at__isnull=False,
                            initial_ack_minutes__gt=0,
                            ack_due_at__isnull=False,
                        )
                    )
                ),
                name='case_review_fields_match_status',
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status='CLOSED', closed_at__isnull=False) & ~Q(resolution_summary=''))
                    | (~Q(status='CLOSED') & Q(closed_at__isnull=True))
                ),
                name='case_closed_fields_match_status',
            ),
            models.CheckConstraint(
                condition=~Q(status='REFERRED') | ~Q(referral_destination=''),
                name='case_referred_has_destination',
            ),
        ]

    def __str__(self) -> str:
        return self.case_number


class TriageReview(models.Model):
    """The single final human severity decision for a case (SDD 4.4.8). AI drafts are not built yet."""

    class Decision(models.TextChoices):
        CONFIRM = 'CONFIRM', 'Confirm AI suggestion'
        OVERRIDE = 'OVERRIDE', 'Override AI suggestion'
        REJECT_MANUAL = 'REJECT_MANUAL', 'Reject AI and classify manually'
        MANUAL = 'MANUAL', 'Manual review'

    review_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    case = models.OneToOneField(CaseRecord, on_delete=models.RESTRICT, db_column='case_id', related_name='review')
    reviewer_membership = models.ForeignKey(
        SchoolMembership, on_delete=models.RESTRICT, db_column='reviewer_membership_id', related_name='reviews'
    )
    decision = models.CharField(max_length=16, choices=Decision.choices, default=Decision.MANUAL)
    confirmed_severity = models.CharField(max_length=8, choices=Severity.choices)
    reason = models.TextField()
    reviewed_at = models.DateTimeField()

    class Meta:
        db_table = 'triage_review'
        constraints = [
            models.CheckConstraint(condition=Q(decision='CONFIRM') | ~Q(reason=''), name='triage_review_reason_required'),
        ]


class CaseAcknowledgement(models.Model):
    """At most one per case; the staff member who accepted responsibility (SDD 4.4.9)."""

    case = models.OneToOneField(
        CaseRecord, on_delete=models.RESTRICT, primary_key=True, db_column='case_id', related_name='acknowledgement'
    )
    actor_membership = models.ForeignKey(
        SchoolMembership, on_delete=models.RESTRICT, db_column='actor_membership_id', related_name='acknowledgements'
    )
    acknowledged_at = models.DateTimeField()

    class Meta:
        db_table = 'case_acknowledgement'
