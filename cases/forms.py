import uuid

from django import forms

from accounts.forms import BootstrapMixin
from schools.models import School, SchoolMembership

from .models import CaseRecord, Report, Severity
from .services import NEXT_STATUSES, active_recipients

TEXT_MIN, TEXT_MAX = 20, 5000


class RecipientChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, membership: SchoolMembership) -> str:
        return f'{membership.account.display_name} ({membership.get_role_display()})'


class IntakeForm(BootstrapMixin, forms.Form):
    intake_request_id = forms.UUIDField(widget=forms.HiddenInput)
    recipient = RecipientChoiceField(
        queryset=SchoolMembership.objects.none(),
        label='Who should read this?',
        empty_label='Choose a trusted adult',
        help_text='Only this adult and the school head will see your report.',
    )
    language_code = forms.ChoiceField(label='Language you are writing in', choices=Report.Language.choices)
    category = forms.ChoiceField(
        label='What is it about? (optional)',
        choices=[('', 'Not sure / skip')] + Report.Category.choices,
        required=False,
    )
    original_text = forms.CharField(
        label='What happened?',
        strip=False,  # BR-02: keep the student's formatting exactly as written.
        widget=forms.Textarea(attrs={'rows': 8, 'maxlength': TEXT_MAX}),
        help_text=f'Write at least {TEXT_MIN} characters. Do not include your name unless you want to.',
    )

    def __init__(self, *args, school: School, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['recipient'].queryset = active_recipients(school)
        if not self.is_bound:
            self.initial['intake_request_id'] = uuid.uuid4()

    def clean_original_text(self) -> str:
        text = self.cleaned_data['original_text']
        if len(text.strip()) < TEXT_MIN:
            raise forms.ValidationError(f'Please write at least {TEXT_MIN} characters so the adult understands.')
        if len(text) > TEXT_MAX:
            raise forms.ValidationError(f'Please keep it under {TEXT_MAX} characters.')
        return text

    def clean_category(self) -> str | None:
        return self.cleaned_data['category'] or None


class ReviewForm(BootstrapMixin, forms.Form):
    severity = forms.ChoiceField(choices=[('', 'Choose severity')] + Severity.choices)
    reason = forms.CharField(
        label='Why this severity?',
        widget=forms.Textarea(attrs={'rows': 3}),
        max_length=2000,
        help_text='Saved with your decision. The student never sees it.',
    )


class StatusForm(BootstrapMixin, forms.Form):
    status = forms.ChoiceField(
        label='Move case to',
        choices=[
            (CaseRecord.Status.IN_PROGRESS, 'In progress'),
            (CaseRecord.Status.REFERRED, 'Referred'),
            (CaseRecord.Status.CLOSED, 'Closed'),
        ],
    )
    referral_destination = forms.CharField(
        label='Referred to', max_length=200, required=False, help_text='Required when you refer the case.'
    )
    resolution_summary = forms.CharField(
        label='Resolution',
        widget=forms.Textarea(attrs={'rows': 3}),
        required=False,
        help_text='Required when you close the case.',
    )

    def __init__(self, *args, case: CaseRecord, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        allowed = NEXT_STATUSES.get(case.status, set())
        self.fields['status'].choices = [c for c in self.fields['status'].choices if c[0] in allowed]


class ReassignForm(BootstrapMixin, forms.Form):
    new_owner = RecipientChoiceField(queryset=SchoolMembership.objects.none(), label='Give case to')

    def __init__(self, *args, case: CaseRecord, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['new_owner'].queryset = (
            SchoolMembership.objects.filter(school_id=case.report.school_id, is_active=True, account__is_active=True)
            .exclude(pk=case.owner_membership_id)
            .select_related('account')
        )


class CaseFilterForm(BootstrapMixin, forms.Form):
    status = forms.ChoiceField(choices=[('', 'All statuses')] + CaseRecord.Status.choices, required=False)
    severity = forms.ChoiceField(choices=[('', 'All severities')] + Severity.choices, required=False)
