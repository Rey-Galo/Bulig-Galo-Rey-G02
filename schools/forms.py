from django import forms

from accounts.forms import BootstrapMixin

from .models import School, SchoolMembership


class JoinSchoolForm(BootstrapMixin, forms.ModelForm):
    """Staff join a school themselves. SCHOOL_HEAD is only granted through the Django admin."""

    role = forms.ChoiceField(
        choices=[
            (SchoolMembership.Role.TEACHER, SchoolMembership.Role.TEACHER.label),
            (SchoolMembership.Role.GUIDANCE, SchoolMembership.Role.GUIDANCE.label),
        ]
    )

    class Meta:
        model = SchoolMembership
        fields = ('school', 'role', 'is_trusted_recipient')

    def __init__(self, *args, account, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.account = account
        self.fields['school'].queryset = School.objects.filter(is_active=True)
        self.fields['school'].empty_label = 'Choose a school'

    def clean_school(self) -> School:
        school = self.cleaned_data['school']
        if SchoolMembership.objects.filter(school=school, account=self.account, is_active=True).exists():
            raise forms.ValidationError('You already belong to this school.')
        return school

    def save(self, commit: bool = True) -> SchoolMembership:
        # Rejoining reuses the switched-off membership kept for case history (one per school).
        old = SchoolMembership.objects.filter(school=self.cleaned_data['school'], account=self.account).first()
        if old:
            old.role = self.cleaned_data['role']
            old.is_trusted_recipient = self.cleaned_data['is_trusted_recipient']
            old.is_active = True
            old.save(update_fields=['role', 'is_trusted_recipient', 'is_active'])
            return old
        self.instance.account = self.account
        return super().save(commit)


class MembershipEditForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = SchoolMembership
        fields = ('is_trusted_recipient',)
