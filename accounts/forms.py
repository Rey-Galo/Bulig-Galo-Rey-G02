from django import forms
from django.contrib.auth.forms import AuthenticationForm, BaseUserCreationForm, UserChangeForm

from .models import StaffAccount


class BootstrapMixin:
    """Render with templates/forms/bootstrap.html; invalid inputs get Bootstrap's red border."""

    template_name = 'forms/bootstrap.html'

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

    def full_clean(self) -> None:
        super().full_clean()
        for name in self.errors:
            if name in self.fields:
                self.fields[name].widget.attrs['class'] += ' is-invalid'


class LoginForm(BootstrapMixin, AuthenticationForm):
    pass


class EmailUniqueMixin:
    """Lowercase the email and reject duplicates regardless of letter case."""

    def clean_email(self) -> str:
        email = self.cleaned_data['email'].strip().lower()
        taken = StaffAccount.objects.filter(email__iexact=email)
        if self.instance.pk:
            taken = taken.exclude(pk=self.instance.pk)
        if taken.exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class RegistrationForm(BootstrapMixin, EmailUniqueMixin, BaseUserCreationForm):
    """Public sign-up. Always creates a plain STAFF account; the role is not user-selectable."""

    class Meta:
        model = StaffAccount
        fields = ('display_name', 'email')
        labels = {'display_name': 'Full name'}


class ProfileForm(BootstrapMixin, EmailUniqueMixin, forms.ModelForm):
    class Meta:
        model = StaffAccount
        fields = ('display_name', 'email')
        labels = {'display_name': 'Full name'}


class AdminAccountCreationForm(EmailUniqueMixin, BaseUserCreationForm):
    class Meta:
        model = StaffAccount
        fields = ('email', 'display_name', 'account_type', 'division')


class AdminAccountChangeForm(UserChangeForm):
    class Meta:
        model = StaffAccount
        fields = '__all__'
