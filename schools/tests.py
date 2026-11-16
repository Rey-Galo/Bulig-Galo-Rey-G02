from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from accounts.models import Division, StaffAccount
from accounts.tests import PASSWORD, make_account

from .models import School, SchoolMembership


def make_school(code: str = 'NHS', **extra) -> School:
    division, _ = Division.objects.get_or_create(division_code='DIV', defaults={'name': 'Division'})
    return School.objects.create(division=division, school_code=code, name=f'{code} School', is_active=True, **extra)


class MembershipCrudTests(TestCase):
    def setUp(self):
        self.school = make_school()
        self.staff = make_account('staff@school.ph')
        self.client.force_login(self.staff)

    def test_join_creates_membership_for_logged_in_user(self):
        response = self.client.post(
            reverse('schools:membership_join'),
            {'school': self.school.pk, 'role': 'GUIDANCE', 'is_trusted_recipient': 'on'},
            follow=True,
        )
        membership = SchoolMembership.objects.get()
        self.assertEqual(membership.account, self.staff)
        self.assertTrue(membership.is_trusted_recipient)
        self.assertContains(response, 'You joined')

    def test_cannot_self_assign_school_head_or_join_twice(self):
        url = reverse('schools:membership_join')
        response = self.client.post(url, {'school': self.school.pk, 'role': 'SCHOOL_HEAD'})
        self.assertContains(response, 'Select a valid choice')
        self.client.post(url, {'school': self.school.pk, 'role': 'TEACHER'})
        response = self.client.post(url, {'school': self.school.pk, 'role': 'TEACHER'})
        self.assertContains(response, 'already belong')
        self.assertEqual(SchoolMembership.objects.count(), 1)

    def test_inactive_school_cannot_be_joined(self):
        closed = make_school('OLD')
        School.objects.filter(pk=closed.pk).update(is_active=False)
        response = self.client.post(reverse('schools:membership_join'), {'school': closed.pk, 'role': 'TEACHER'})
        self.assertContains(response, 'Select a valid choice')

    def test_edit_and_leave_own_membership(self):
        membership = SchoolMembership.objects.create(school=self.school, account=self.staff)
        self.client.post(reverse('schools:membership_edit', args=[membership.pk]), {'is_trusted_recipient': 'on'})
        membership.refresh_from_db()
        self.assertTrue(membership.is_trusted_recipient)
        self.client.post(reverse('schools:membership_leave', args=[membership.pk]))
        self.assertFalse(SchoolMembership.objects.exists())

    def test_other_users_membership_is_404(self):
        other = SchoolMembership.objects.create(school=self.school, account=make_account('other@school.ph'))
        self.assertEqual(self.client.post(reverse('schools:membership_leave', args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('schools:membership_edit', args=[other.pk])).status_code, 404)
        self.assertTrue(SchoolMembership.objects.filter(pk=other.pk).exists())

    def test_admin_roles_cannot_use_memberships(self):
        self.client.force_login(make_account('p@school.ph', StaffAccount.AccountType.PLATFORM_ADMIN))
        self.assertEqual(self.client.get(reverse('schools:membership_list')).status_code, 403)

    def test_anonymous_is_sent_to_login(self):
        self.client.logout()
        response = self.client.get(reverse('schools:membership_list'))
        self.assertRedirects(response, reverse('accounts:login') + '?next=' + reverse('schools:membership_list'))


class SeedDemoTests(TestCase):
    def test_seed_is_repeatable(self):
        call_command('seed_demo', password=PASSWORD, stdout=StringIO())
        call_command('seed_demo', password=PASSWORD, stdout=StringIO())
        self.assertEqual(School.objects.count(), 1)
        self.assertEqual(SchoolMembership.objects.count(), 3)
        self.assertTrue(self.client.login(email='head@bulig.test', password=PASSWORD))
