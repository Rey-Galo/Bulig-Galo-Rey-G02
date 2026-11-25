import uuid
from datetime import timedelta

from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import StaffAccount
from accounts.tests import make_account
from schools.models import SchoolMembership
from schools.tests import make_school

from .models import CaseRecord, Report

Status = CaseRecord.Status
Role = SchoolMembership.Role
TEXT = 'Someone keeps taking my lunch money every recess.'


class CaseTestBase(TestCase):
    def setUp(self):
        self.school = make_school(high_ack_minutes=90)
        self.teacher = self.member('teacher@s.ph', Role.TEACHER, trusted=True)
        self.head = self.member('head@s.ph', Role.SCHOOL_HEAD)
        self.colleague = self.member('colleague@s.ph', Role.GUIDANCE)

    def member(self, email, role, trusted=False, school=None):
        return SchoolMembership.objects.create(
            school=school or self.school, account=make_account(email), role=role, is_trusted_recipient=trusted
        )

    def intake(self, **overrides):
        data = {
            'intake_request_id': str(uuid.uuid4()),
            'recipient': self.teacher.pk,
            'language_code': 'en',
            'category': 'BULLYING',
            'original_text': TEXT,
        } | overrides
        return self.client.post(reverse('cases:intake_form', args=[self.school.pk]), data, follow=True), data

    def make_case(self) -> CaseRecord:
        self.intake()
        return CaseRecord.objects.get()

    def act(self, who, name, case, **data):
        self.client.force_login(who.account)
        return self.client.post(reverse(f'cases:case_{name}', args=[case.pk]), data, follow=True)


class IntakeTests(CaseTestBase):
    def test_anonymous_report_creates_pending_case_owned_by_recipient(self):
        response, _ = self.intake()
        self.assertContains(response, 'Your report was sent')
        case = CaseRecord.objects.select_related('report').get()
        self.assertEqual(case.status, Status.PENDING_REVIEW)
        self.assertEqual(case.owner_membership, self.teacher)
        self.assertEqual(case.report.original_text, TEXT)
        self.assertIsNone(case.ack_due_at)

    def test_retry_with_same_request_id_creates_one_report(self):
        _, data = self.intake()
        self.client.post(reverse('cases:intake_form', args=[self.school.pk]), data)
        self.assertEqual(Report.objects.count(), 1)
        changed = data | {'original_text': TEXT + ' Also yesterday.'}
        response = self.client.post(reverse('cases:intake_form', args=[self.school.pk]), changed)
        self.assertContains(response, 'already submitted')
        self.assertEqual(Report.objects.count(), 1)

    def test_rejects_short_text_and_non_recipient(self):
        response, _ = self.intake(original_text='   too short        ')
        self.assertContains(response, 'at least 20 characters')
        response, _ = self.intake(recipient=self.colleague.pk)  # not opted in
        self.assertContains(response, 'Select a valid choice')
        other = self.member('x@other.ph', Role.TEACHER, trusted=True, school=make_school('OTH'))
        response, _ = self.intake(recipient=other.pk)  # other school
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(Report.objects.exists())

    def test_school_without_recipients_is_not_offered(self):
        empty = make_school('EMP')
        self.assertNotContains(self.client.get(reverse('cases:intake_school')), empty.name)
        self.assertEqual(self.client.get(reverse('cases:intake_form', args=[empty.pk])).status_code, 404)


class WorkflowTests(CaseTestBase):
    def test_full_flow_review_acknowledge_refer_close(self):
        case = self.make_case()
        self.act(self.teacher, 'review', case, severity='HIGH', reason='Repeated theft')
        case.refresh_from_db()
        self.assertEqual(case.status, Status.OPEN)
        self.assertEqual(case.initial_ack_minutes, 90)
        self.assertEqual(case.ack_due_at, case.reviewed_at + timedelta(minutes=90))

        self.act(self.teacher, 'acknowledge', case)
        self.act(self.teacher, 'status', case, status='IN_PROGRESS')
        response = self.act(self.teacher, 'status', case, status='REFERRED')
        self.assertContains(response, 'Say where the case was referred')
        self.act(self.teacher, 'status', case, status='REFERRED', referral_destination='DSWD Cebu')
        response = self.act(self.teacher, 'status', case, status='CLOSED')
        self.assertContains(response, 'resolution')
        response = self.act(self.teacher, 'status', case, status='CLOSED', resolution_summary='Parents met; resolved.')
        self.assertContains(response, 'Case status updated')
        case.refresh_from_db()
        self.assertEqual(case.status, Status.CLOSED)
        self.assertEqual(case.acknowledgement.actor_membership, self.teacher)
        self.assertIsNotNone(case.closed_at)

    def test_cannot_skip_steps_or_review_twice(self):
        case = self.make_case()
        response = self.act(self.teacher, 'acknowledge', case)
        self.assertContains(response, 'Only an open, reviewed case')
        self.act(self.teacher, 'review', case, severity='LOW', reason='Minor')
        response = self.act(self.head, 'review', case, severity='HIGH', reason='Changed mind')
        self.assertContains(response, 'already been reviewed')
        case.refresh_from_db()
        self.assertEqual(case.confirmed_severity, 'LOW')

    def test_review_requires_reason(self):
        case = self.make_case()
        response = self.act(self.teacher, 'review', case, severity='HIGH', reason='')
        self.assertContains(response, 'This field is required')
        case.refresh_from_db()
        self.assertEqual(case.status, Status.PENDING_REVIEW)

    def test_head_reassigns_and_original_recipient_is_kept(self):
        case = self.make_case()
        response = self.act(self.teacher, 'reassign', case, new_owner=self.colleague.pk)
        self.assertEqual(response.status_code, 403)
        self.act(self.head, 'reassign', case, new_owner=self.colleague.pk)
        case.refresh_from_db()
        self.assertEqual(case.owner_membership, self.colleague)
        self.assertEqual(case.report.recipient_membership, self.teacher)
        # The original recipient can still read it, but no longer change it.
        response = self.act(self.teacher, 'review', case, severity='LOW', reason='x')
        self.assertEqual(response.status_code, 403)


class AccessTests(CaseTestBase):
    def test_colleague_without_link_cannot_see_case(self):
        case = self.make_case()
        self.client.force_login(self.colleague.account)
        self.assertEqual(self.client.get(reverse('cases:case_detail', args=[case.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('cases:case_list')), case.case_number)

    def test_head_and_recipient_see_case(self):
        case = self.make_case()
        for member in (self.teacher, self.head):
            self.client.force_login(member.account)
            self.assertContains(self.client.get(reverse('cases:case_detail', args=[case.pk])), TEXT)

    def test_admins_and_anonymous_users_cannot_open_cases(self):
        case = self.make_case()
        url = reverse('cases:case_detail', args=[case.pk])
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)
        admin = make_account('p@s.ph', StaffAccount.AccountType.PLATFORM_ADMIN)
        self.client.force_login(admin)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_division_dashboard_shows_counts_without_report_text(self):
        case = self.make_case()
        division_admin = make_account(
            'd@s.ph', StaffAccount.AccountType.DIVISION_ADMIN, division=self.school.division
        )
        self.client.force_login(division_admin)
        response = self.client.get(reverse('accounts:division_dashboard'))
        self.assertContains(response, self.school.name)
        self.assertEqual(response.context['totals']['unreviewed'], 1)
        self.assertNotContains(response, TEXT)
        self.assertNotContains(response, case.case_number)

    def test_staff_dashboard_counts_owned_cases(self):
        self.make_case()
        self.client.force_login(self.teacher.account)
        response = self.client.get(reverse('accounts:staff_dashboard'))
        self.assertEqual(response.context['counts']['to_review'], 1)


class LeaveSchoolTests(CaseTestBase):
    def test_cannot_leave_while_owning_open_case_then_deactivates_after_close(self):
        case = self.make_case()
        url = reverse('schools:membership_leave', args=[self.teacher.pk])
        self.client.force_login(self.teacher.account)
        response = self.client.post(url, follow=True)
        self.assertContains(response, 'still own 1 open case')
        CaseRecord.objects.filter(pk=case.pk).update(
            status=Status.CLOSED, confirmed_severity='LOW', reviewed_at=case.opened_at, initial_ack_minutes=1,
            ack_due_at=case.opened_at, closed_at=case.opened_at, resolution_summary='done',
        )
        self.client.post(url)
        self.teacher.refresh_from_db()
        self.assertFalse(self.teacher.is_active)  # kept for history, switched off
        self.client.post(reverse('schools:membership_join'), {'school': self.school.pk, 'role': 'GUIDANCE'})
        self.teacher.refresh_from_db()
        self.assertTrue(self.teacher.is_active)
        self.assertEqual(self.teacher.role, Role.GUIDANCE)


class ErrorHandlingTests(CaseTestBase):
    def test_unknown_case_id_renders_custom_404_page(self):
        self.client.force_login(self.teacher.account)
        with override_settings(DEBUG=False):
            response = self.client.get(reverse('cases:case_detail', args=[uuid.uuid4()]))
        self.assertEqual(response.status_code, 404)
        self.assertTemplateUsed(response, '404.html')

    def test_malformed_case_id_is_404_not_a_crash(self):
        self.client.force_login(self.teacher.account)
        self.assertEqual(self.client.get('/cases/not-a-uuid/').status_code, 404)

    def test_case_actions_reject_get_with_405(self):
        case = self.make_case()
        self.client.force_login(self.teacher.account)
        for name in ('review', 'acknowledge', 'status', 'reassign'):
            with self.subTest(action=name):
                self.assertEqual(self.client.get(reverse(f'cases:case_{name}', args=[case.pk])).status_code, 405)

    def test_post_without_csrf_token_is_rejected_and_case_unchanged(self):
        case = self.make_case()
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.teacher.account)
        response = strict.post(reverse('cases:case_review', args=[case.pk]), {'severity': 'HIGH', 'reason': 'x'})
        self.assertEqual(response.status_code, 403)
        case.refresh_from_db()
        self.assertEqual(case.status, Status.PENDING_REVIEW)

    def test_500_page_renders_standalone_with_no_context(self):
        self.assertIn('Something went wrong', render_to_string('500.html'))

    def test_unlinked_colleague_cannot_review_or_change_status(self):
        case = self.make_case()
        self.client.force_login(self.colleague.account)
        for name, data in (('review', {'severity': 'HIGH', 'reason': 'x'}), ('status', {'status': 'IN_PROGRESS'})):
            with self.subTest(action=name):
                response = self.client.post(reverse(f'cases:case_{name}', args=[case.pk]), data)
                self.assertEqual(response.status_code, 404)
        case.refresh_from_db()
        self.assertEqual(case.status, Status.PENDING_REVIEW)
        self.assertIsNone(case.confirmed_severity)
