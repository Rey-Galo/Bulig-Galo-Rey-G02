import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from accounts.models import Division


class School(models.Model):
    """A school that receives reports, with its acknowledgement windows (SDD 4.4.2)."""

    school_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    division = models.ForeignKey(Division, on_delete=models.RESTRICT, db_column='division_id', related_name='schools')
    school_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    # Public intake is only offered for active schools.
    is_active = models.BooleanField(default=False)
    high_ack_minutes = models.IntegerField(default=120, validators=[MinValueValidator(1)])
    moderate_ack_minutes = models.IntegerField(default=1440, validators=[MinValueValidator(1)])
    low_ack_minutes = models.IntegerField(default=4320, validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'school'
        ordering = ['name']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(high_ack_minutes__gt=0, moderate_ack_minutes__gt=0, low_ack_minutes__gt=0),
                name='school_ack_minutes_positive',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.name} ({self.school_code})'


class SchoolMembership(models.Model):
    """Links a staff account to a school with a school-specific role (SDD 4.4.4)."""

    class Role(models.TextChoices):
        TEACHER = 'TEACHER', 'Teacher'
        GUIDANCE = 'GUIDANCE', 'Guidance personnel'
        SCHOOL_HEAD = 'SCHOOL_HEAD', 'School head'

    membership_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school = models.ForeignKey(School, on_delete=models.RESTRICT, db_column='school_id', related_name='memberships')
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, db_column='account_id', related_name='memberships'
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.TEACHER)
    is_trusted_recipient = models.BooleanField(
        'Receive student reports',
        default=False,
        help_text='Students can pick you as their trusted adult when this is on.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'school_membership'
        ordering = ['school__name']
        constraints = [
            models.UniqueConstraint(fields=['school', 'account'], name='school_membership_one_per_school'),
        ]

    def __str__(self) -> str:
        return f'{self.account.display_name} · {self.get_role_display()} · {self.school.school_code}'
