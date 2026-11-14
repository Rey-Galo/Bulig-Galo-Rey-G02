from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from .models import Division, StaffAccount

PASSWORD = 'Correct-Horse-42'


def make_account(email: str, account_type: str = StaffAccount.AccountType.STAFF, **extra) -> StaffAccount:
    return StaffAccount.objects.create_user(email, 'Test User', PASSWORD, account_type=account_type, **extra)


class RegistrationTests(TestCase):
    def post(self, **overrides):
        data = {'display_name': 'Ana Cruz', 'email': 'Ana@School.ph', 'password1': PASSWORD, 'password2': PASSWORD}
        return self.client.post(reverse('accounts:register'), data | overrides, follow=True)

    def test_creates_staff_account_with_argon2_hash(self):
        response = self.post()
        account = StaffAccount.objects.get()
        self.assertEqual(account.email, 'ana@school.ph')
        self.assertEqual(account.account_type, StaffAccount.AccountType.STAFF)
        self.assertTrue(account.password.startswith('argon2$'))
        self.assertContains(response, 'Account created')

    def test_role_cannot_be_chosen_on_signup(self):
        self.post(account_type=StaffAccount.AccountType.PLATFORM_ADMIN)
        self.assertEqual(StaffAccount.objects.get().account_type, StaffAccount.AccountType.STAFF)

    def test_rejects_duplicate_email_any_case(self):
        make_account('ana@school.ph')
        response = self.post(email='ANA@school.ph')
        self.assertContains(response, 'already exists')
        self.assertEqual(StaffAccount.objects.count(), 1)

    def test_rejects_mismatched_passwords_and_bad_email(self):
        response = self.post(email='not-an-email', password2='different-pass-99')
        self.assertContains(response, 'Enter a valid email address')
        self.assertContains(response, 'password fields didn')
        self.assertFalse(StaffAccount.objects.exists())

    def test_rejects_missing_fields(self):
        response = self.post(display_name='')
        self.assertContains(response, 'This field is required')

    def test_invalid_field_gets_bootstrap_error_style(self):
        response = self.post(display_name='')
        self.assertContains(response, 'class="form-control is-invalid"')
        self.assertContains(response, 'invalid-feedback')


class LoginAndRoleTests(TestCase):
    def setUp(self):
        self.division = Division.objects.create(division_code='CEBU-CITY', name='Cebu City Division')
        self.staff = make_account('staff@school.ph')
        self.division_admin = make_account(
            'div@deped.ph', StaffAccount.AccountType.DIVISION_ADMIN, division=self.division
        )
        self.platform_admin = make_account('root@bulig.ph', StaffAccount.AccountType.PLATFORM_ADMIN)

    def login(self, email: str):
        return self.client.post(reverse('accounts:login'), {'username': email, 'password': PASSWORD})

    def test_each_role_lands_on_own_dashboard(self):
        cases = [
            ('staff@school.ph', 'accounts:staff_dashboard'),
            ('DIV@deped.ph', 'accounts:division_dashboard'),
            ('root@bulig.ph', 'accounts:platform_dashboard'),
        ]
        for email, dashboard in cases:
            with self.subTest(email=email):
                self.login(email)
                response = self.client.get(reverse('accounts:dashboard'))
                self.assertRedirects(response, reverse(dashboard))
                self.client.logout()

    def test_platform_dashboard_shows_counts_per_type(self):
        self.client.force_login(self.platform_admin)
        response = self.client.get(reverse('accounts:platform_dashboard'))
        for label in ('School staff accounts', 'Divisions', 'root@bulig.ph'):
            self.assertContains(response, label)

    def test_invalid_credentials_show_error(self):
        response = self.client.post(reverse('accounts:login'), {'username': 'staff@school.ph', 'password': 'wrong'})
        self.assertContains(response, 'Please enter a correct')

    def test_staff_cannot_open_other_dashboards(self):
        self.client.force_login(self.staff)
        for name in ('accounts:division_dashboard', 'accounts:platform_dashboard'):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 403)
                self.assertContains(response, 'Access denied', status_code=403)

    def test_anonymous_user_redirected_to_login(self):
        for name in ('accounts:staff_dashboard', 'accounts:platform_dashboard', 'accounts:profile'):
            with self.subTest(name=name):
                url = reverse(name)
                self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_logout_ends_session(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('accounts:logout'))
        self.assertEqual(self.client.get(reverse('accounts:profile')).status_code, 302)

    def test_division_required_only_for_division_admin(self):
        with self.assertRaises(IntegrityError):
            make_account('bad@school.ph', division=self.division)


class ProfileTests(TestCase):
    def setUp(self):
        self.me = make_account('me@school.ph')
        self.other = make_account('other@school.ph')
        self.client.force_login(self.me)

    def test_view_shows_own_info(self):
        self.assertContains(self.client.get(reverse('accounts:profile')), 'me@school.ph')

    def test_update_changes_only_own_account(self):
        response = self.client.post(
            reverse('accounts:profile_edit'), {'display_name': 'New Name', 'email': 'new@school.ph'}, follow=True
        )
        self.assertContains(response, 'Profile updated')
        self.me.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual((self.me.display_name, self.me.email), ('New Name', 'new@school.ph'))
        self.assertEqual(self.other.email, 'other@school.ph')

    def test_cannot_take_another_accounts_email(self):
        response = self.client.post(
            reverse('accounts:profile_edit'), {'display_name': 'Me', 'email': 'OTHER@school.ph'}
        )
        self.assertContains(response, 'already exists')
