from django.contrib import messages
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
    if request.method == 'POST':
        membership.delete()
        messages.success(request, f'You left {membership.school.name}.')
        return redirect('schools:membership_list')
    return render(request, 'schools/membership_leave.html', {'membership': membership})
