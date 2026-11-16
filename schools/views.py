from django.contrib import messages
from django.db.models import RestrictedError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import StaffAccount
from accounts.views import role_required

from .forms import JoinSchoolForm, MembershipEditForm
from .models import SchoolMembership

STAFF = StaffAccount.AccountType.STAFF


def _own_membership(request: HttpRequest, pk) -> SchoolMembership:
    # Scoped to request.user, so another account's membership id gives 404.
    return get_object_or_404(SchoolMembership.objects.select_related('school'), pk=pk, account=request.user)


@role_required(STAFF)
def membership_list(request: HttpRequest) -> HttpResponse:
    memberships = request.user.memberships.select_related('school')
    return render(request, 'schools/membership_list.html', {'memberships': memberships})


@role_required(STAFF)
def membership_join(request: HttpRequest) -> HttpResponse:
    form = JoinSchoolForm(request.POST or None, account=request.user)
    if request.method == 'POST':
        if form.is_valid():
            membership = form.save()
            messages.success(request, f'You joined {membership.school.name}.')
            return redirect('schools:membership_list')
        messages.error(request, 'Please fix the errors below.')
    return render(request, 'schools/membership_form.html', {'form': form, 'title': 'Join a school'})


@role_required(STAFF)
def membership_edit(request: HttpRequest, pk) -> HttpResponse:
    membership = _own_membership(request, pk)
    form = MembershipEditForm(request.POST or None, instance=membership)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, f'Updated your settings for {membership.school.name}.')
            return redirect('schools:membership_list')
        messages.error(request, 'Please fix the errors below.')
    context = {'form': form, 'title': f'Settings for {membership.school.name}'}
    return render(request, 'schools/membership_form.html', context)


@role_required(STAFF)
def membership_leave(request: HttpRequest, pk) -> HttpResponse:
    membership = _own_membership(request, pk)
    # BR-26: hand over open cases first.
    open_cases = membership.owned_cases.exclude(status='CLOSED').count()
    if request.method == 'POST':
        if open_cases:
            messages.error(request, f'You still own {open_cases} open case(s). Ask your school head to reassign them first.')
            return redirect('schools:membership_list')
        try:
            membership.delete()
        except RestrictedError:
            # BR-28: case history points at this membership, so keep the row and switch it off instead.
            membership.is_active = False
            membership.is_trusted_recipient = False
            membership.save(update_fields=['is_active', 'is_trusted_recipient'])
        messages.success(request, f'You left {membership.school.name}.')
        return redirect('schools:membership_list')
    return render(request, 'schools/membership_leave.html', {'membership': membership, 'open_cases': open_cases})
