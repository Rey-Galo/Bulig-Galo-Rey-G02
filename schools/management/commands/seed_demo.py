from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Division, StaffAccount
from schools.models import School, SchoolMembership

AccountType = StaffAccount.AccountType
Role = SchoolMembership.Role

# (email, display name, account type, school role or None)
DEMO_ACCOUNTS = [
    ('head@bulig.test', 'Maria Santos', AccountType.STAFF, Role.SCHOOL_HEAD),
    ('teacher@bulig.test', 'Jose Reyes', AccountType.STAFF, Role.TEACHER),
    ('guidance@bulig.test', 'Liza Cruz', AccountType.STAFF, Role.GUIDANCE),
    ('division@bulig.test', 'Ramon Dela Cruz', AccountType.DIVISION_ADMIN, None),
    ('platform@bulig.test', 'Platform Admin', AccountType.PLATFORM_ADMIN, None),
]


class Command(BaseCommand):
    help = 'Create a demo division, school and test accounts. Safe to run more than once.'

    def add_arguments(self, parser) -> None:
        parser.add_argument('--password', required=True, help='Password for every demo account.')

    @transaction.atomic
    def handle(self, *args, password: str, **options) -> None:
        division, _ = Division.objects.get_or_create(division_code='DEMO-CEBU', defaults={'name': 'Demo Cebu Division'})
        school, _ = School.objects.get_or_create(
            school_code='DEMO-NHS',
            defaults={'name': 'Demo National High School', 'division': division, 'is_active': True},
        )
        for email, name, account_type, role in DEMO_ACCOUNTS:
            account = StaffAccount.objects.filter(email__iexact=email).first()
            if account is None:
                extra = {'division': division} if account_type == AccountType.DIVISION_ADMIN else {}
                if account_type == AccountType.PLATFORM_ADMIN:
                    account = StaffAccount.objects.create_superuser(email, name, password)
                else:
                    account = StaffAccount.objects.create_user(email, name, password, account_type=account_type, **extra)
            if role:
                SchoolMembership.objects.get_or_create(
                    school=school, account=account, defaults={'role': role, 'is_trusted_recipient': True}
                )
            self.stdout.write(f'{email} ({account_type}{" / " + role if role else ""})')
        self.stdout.write(self.style.SUCCESS(f'Demo data ready for {school}.'))
