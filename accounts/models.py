import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.db.models.functions import Lower


class Division(models.Model):
    """Administrative group of schools (SDD 4.4.1)."""

    division_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    division_code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=150)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'division'
        ordering = ['name']

    def __str__(self) -> str:
        return f'{self.name} ({self.division_code})'


class StaffAccountManager(BaseUserManager):
    def get_by_natural_key(self, username: str) -> 'StaffAccount':
        # Emails are stored lowercase, so login must match case-insensitively.
        return self.get(email__iexact=username)

    def create_user(self, email: str, display_name: str, password: str | None = None, **extra) -> 'StaffAccount':
        if not email:
            raise ValueError('An email address is required.')
        account = self.model(email=self.normalize_email(email).lower(), display_name=display_name, **extra)
        account.set_password(password)
        account.save(using=self._db)
        return account

    def create_superuser(self, email: str, display_name: str, password: str | None = None, **extra) -> 'StaffAccount':
        extra.setdefault('account_type', StaffAccount.AccountType.PLATFORM_ADMIN)
        extra.setdefault('is_staff', True)
        extra.setdefault('is_superuser', True)
        return self.create_user(email, display_name, password, **extra)


class StaffAccount(AbstractBaseUser, PermissionsMixin):
    """Authenticated adult account; students never get accounts (SDD 4.4.3)."""

    class AccountType(models.TextChoices):
        STAFF = 'STAFF', 'School staff'
        DIVISION_ADMIN = 'DIVISION_ADMIN', 'Division administrator'
        PLATFORM_ADMIN = 'PLATFORM_ADMIN', 'Platform administrator'

    account_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(max_length=254, unique=True)
    display_name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.STAFF)
    division = models.ForeignKey(
        Division,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        db_column='division_id',
        related_name='accounts',
    )
    is_active = models.BooleanField(default=True)
    # Django admin site access only; not a Bulig role.
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = StaffAccountManager()

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['display_name']

    class Meta:
        db_table = 'staff_account'
        constraints = [
            models.UniqueConstraint(Lower('email'), name='staff_account_email_ci_unique'),
            # division_id is required only for DIVISION_ADMIN and NULL otherwise.
            models.CheckConstraint(
                condition=(
                    models.Q(account_type='DIVISION_ADMIN', division__isnull=False)
                    | (~models.Q(account_type='DIVISION_ADMIN') & models.Q(division__isnull=True))
                ),
                name='staff_account_division_matches_type',
                violation_error_message='A division is required for division administrators and not allowed otherwise.',
            ),
        ]

    def __str__(self) -> str:
        return f'{self.display_name} <{self.email}>'
