from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from cases.models import CaseRecord
from cases.services import visible_cases
from schools.models import School

from .forms import ProfileForm, RegistrationForm
from .models import Division, StaffAccount

AccountType = StaffAccount.AccountType

DASHBOARD_FOR_TYPE = {
    AccountType.STAFF: 'accounts:staff_dashboard',
    AccountType.DIVISION_ADMIN: 'accounts:division_dashboard',
    AccountType.PLATFORM_ADMIN: 'accounts:platform_dashboard',
}


def role_required(account_type: str):
    """Allow only logged-in accounts of one type; others get 403, anonymous users go to login."""

    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            if request.user.account_type != account_type:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def register(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    form = RegistrationForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Account created. You can now log in.')
            return redirect('accounts:login')
        messages.error(request, 'Please fix the errors below.')
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    return redirect(DASHBOARD_FOR_TYPE[request.user.account_type])


@role_required(AccountType.STAFF)
def staff_dashboard(request: HttpRequest) -> HttpResponse:
    memberships = request.user.memberships.select_related('school')
    Status = CaseRecord.Status
    owned = CaseRecord.objects.filter(owner_membership__account=request.user, owner_membership__is_active=True)
    counts = owned.aggregate(
        to_review=Count('pk', filter=Q(status=Status.PENDING_REVIEW)),
        to_acknowledge=Count('pk', filter=Q(status=Status.OPEN)),
        working=Count('pk', filter=Q(status__in=[Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.REFERRED])),
    )
    context = {
        'memberships': memberships,
        'counts': counts,
        'recent_cases': visible_cases(request.user).exclude(status=Status.CLOSED)[:5],
    }
    return render(request, 'accounts/dashboard_staff.html', context)


def _case_count(status_q: Q) -> Count:
    return Count('reports__case', filter=status_q)


@role_required(AccountType.DIVISION_ADMIN)
def division_dashboard(request: HttpRequest) -> HttpResponse:
    # BR-22: counts per school only. No report text, case ids or case numbers leave this query.
    Status = CaseRecord.Status
    schools = list(
        School.objects.filter(division=request.user.division)
        .annotate(
            unreviewed=_case_count(Q(reports__case__status=Status.PENDING_REVIEW)),
            unacknowledged=_case_count(Q(reports__case__status=Status.OPEN)),
            overdue=_case_count(Q(reports__case__status=Status.OPEN, reports__case__ack_due_at__lt=timezone.now())),
            active=_case_count(
                Q(reports__case__status__in=[Status.ACKNOWLEDGED, Status.IN_PROGRESS, Status.REFERRED])
            ),
            closed=_case_count(Q(reports__case__status=Status.CLOSED)),
        )
        .values('name', 'school_code', 'unreviewed', 'unacknowledged', 'overdue', 'active', 'closed')
    )
    keys = ('unreviewed', 'unacknowledged', 'overdue', 'active', 'closed')
    totals = {key: sum(school[key] for school in schools) for key in keys}
    context = {'division': request.user.division, 'schools': schools, 'totals': totals}
    return render(request, 'accounts/dashboard_division.html', context)


@role_required(AccountType.PLATFORM_ADMIN)
def platform_dashboard(request: HttpRequest) -> HttpResponse:
    counts = dict(
        StaffAccount.objects.values_list('account_type').annotate(n=Count('pk')).values_list('account_type', 'n')
    )
    context = {
        'account_counts': [(label, counts.get(value, 0)) for value, label in AccountType.choices],
        'division_count': Division.objects.count(),
        'school_count': School.objects.count(),
        'recent_accounts': StaffAccount.objects.order_by('-created_at')[:5],
    }
    return render(request, 'accounts/dashboard_platform.html', context)


@login_required
def profile(request: HttpRequest) -> HttpResponse:
    # Always the logged-in account: there is no id in the URL to tamper with.
    return render(request, 'accounts/profile.html', {'account': request.user})


@login_required
def profile_edit(request: HttpRequest) -> HttpResponse:
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated.')
            return redirect('accounts:profile')
        messages.error(request, 'Please fix the errors below.')
    return render(request, 'accounts/profile_edit.html', {'form': form})
