from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import StaffAccount
from accounts.views import role_required

from . import services
from .forms import CaseFilterForm, IntakeForm, ReassignForm, ReviewForm, StatusForm
from .models import CaseRecord

STAFF = StaffAccount.AccountType.STAFF


# Public intake: no login, no student identity (BR-01).


def intake_school(request: HttpRequest) -> HttpResponse:
    schools = services.schools_accepting_reports()
    return render(request, 'cases/intake_school.html', {'schools': schools})


def intake_form(request: HttpRequest, school_id) -> HttpResponse:
    school = get_object_or_404(services.schools_accepting_reports(), pk=school_id)
    form = IntakeForm(request.POST or None, school=school)
    if request.method == 'POST':
        if form.is_valid():
            data = form.cleaned_data
            try:
                services.submit_report(
                    intake_request_id=data['intake_request_id'],
                    school=school,
                    recipient=data['recipient'],
                    language_code=data['language_code'],
                    category=data['category'],
                    original_text=data['original_text'],
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                return redirect('cases:intake_received')
        messages.error(request, 'Please fix the errors below.')
    return render(request, 'cases/intake_form.html', {'form': form, 'school': school})


def intake_received(request: HttpRequest) -> HttpResponse:
    # Generic on purpose: shows nothing about the report, so it reveals nothing if someone else opens it.
    return render(request, 'cases/intake_received.html')


# Staff case desk (BR-07).


@role_required(STAFF)
def case_list(request: HttpRequest) -> HttpResponse:
    cases = services.visible_cases(request.user)
    filters = CaseFilterForm(request.GET or None)
    if filters.is_valid():
        if filters.cleaned_data['status']:
            cases = cases.filter(status=filters.cleaned_data['status'])
        if filters.cleaned_data['severity']:
            cases = cases.filter(confirmed_severity=filters.cleaned_data['severity'])
    return render(request, 'cases/case_list.html', {'cases': cases, 'filters': filters, 'now': timezone.now()})


def _visible_case(request: HttpRequest, pk) -> CaseRecord:
    # Cases outside the user's access look like they don't exist.
    return get_object_or_404(services.visible_cases(request.user), pk=pk)


@role_required(STAFF)
def case_detail(request: HttpRequest, pk) -> HttpResponse:
    case = _visible_case(request, pk)
    actor = services.acting_membership(request.user, case)
    context = {
        'case': case,
        'can_act': actor is not None,
        'is_head': actor is not None and actor.role == actor.Role.SCHOOL_HEAD,
        'review_form': ReviewForm(),
        'status_form': StatusForm(case=case),
        'reassign_form': ReassignForm(case=case),
        'now': timezone.now(),
    }
    return render(request, 'cases/case_detail.html', context)


def _run(request: HttpRequest, case: CaseRecord, action, success: str, **kwargs) -> HttpResponse:
    try:
        action(case, request.user, **kwargs)
    except ValidationError as error:
        messages.error(request, ' '.join(error.messages))
    else:
        messages.success(request, success)
    return redirect('cases:case_detail', pk=case.pk)


def _form_errors(form) -> str:
    """Flatten form errors into one flash message, e.g. "Resolution: This field is required."."""
    parts = []
    for name, errors in form.errors.items():
        label = form[name].label if name in form.fields else ''
        parts += [f'{label}: {error}' if label else error for error in errors]
    return ' '.join(parts)


@require_POST
@role_required(STAFF)
def case_review(request: HttpRequest, pk) -> HttpResponse:
    case = _visible_case(request, pk)
    form = ReviewForm(request.POST)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return redirect('cases:case_detail', pk=case.pk)
    return _run(request, case, services.review_case, 'Review saved. The acknowledgement clock has started.', **form.cleaned_data)


@require_POST
@role_required(STAFF)
def case_acknowledge(request: HttpRequest, pk) -> HttpResponse:
    case = _visible_case(request, pk)
    return _run(request, case, services.acknowledge_case, 'Case acknowledged. You are responsible for it now.')


@require_POST
@role_required(STAFF)
def case_status(request: HttpRequest, pk) -> HttpResponse:
    case = _visible_case(request, pk)
    form = StatusForm(request.POST, case=case)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return redirect('cases:case_detail', pk=case.pk)
    return _run(request, case, services.change_status, 'Case status updated.', **form.cleaned_data)


@require_POST
@role_required(STAFF)
def case_reassign(request: HttpRequest, pk) -> HttpResponse:
    case = _visible_case(request, pk)
    form = ReassignForm(request.POST, case=case)
    if not form.is_valid():
        messages.error(request, _form_errors(form))
        return redirect('cases:case_detail', pk=case.pk)
    return _run(request, case, services.reassign_case, 'Case reassigned.', **form.cleaned_data)
