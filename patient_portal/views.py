from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import Group
from django.utils import timezone
from dental_office.roles import patient_required
from appointments.models import Appointment, AppointmentRequest
from billing.models import Invoice
from clinical.models import TreatmentRecord, TreatmentPlan
from .forms import AppointmentRequestForm, PatientProfileForm, InviteSetPasswordForm
from .models import PatientInvite


@patient_required
def patient_dashboard(request):
    patient = request.user.patient_profile
    today = timezone.localdate()

    next_appointment = patient.appointments.filter(
        date__gte=today, status='scheduled'
    ).order_by('date', 'start_time').first()

    total_balance = sum(
        inv.balance_due() for inv in patient.invoices.filter(status__in=['pending', 'partial'])
    )

    recent_records = patient.treatment_records.order_by('-date')[:3]

    return render(request, 'patient_portal/dashboard.html', {
        'patient': patient,
        'next_appointment': next_appointment,
        'total_balance': total_balance,
        'recent_records': recent_records,
    })


@patient_required
def patient_appointments(request):
    patient = request.user.patient_profile
    today = timezone.localdate()

    upcoming = patient.appointments.filter(
        date__gte=today, status='scheduled'
    ).order_by('date', 'start_time')

    past = patient.appointments.filter(
        date__lt=today
    ).order_by('-date', '-start_time')[:10]

    AppointmentRequest.objects.expire_stale()
    pending_requests = patient.appointment_requests.filter(status='pending')

    return render(request, 'patient_portal/appointments.html', {
        'patient': patient,
        'upcoming': upcoming,
        'past': past,
        'pending_requests': pending_requests,
    })


@patient_required
def patient_request_appointment(request):
    patient = request.user.patient_profile

    if request.method == 'POST':
        form = AppointmentRequestForm(request.POST)
        if form.is_valid():
            appt_request = form.save(commit=False)
            appt_request.patient = patient
            appt_request.first_name = patient.first_name
            appt_request.last_name = patient.last_name
            appt_request.phone = patient.phone
            appt_request.email = patient.email
            appt_request.save()
            messages.success(request, 'Your appointment request has been submitted. The office will confirm your time shortly.')
            return redirect('patient_appointments')
    else:
        form = AppointmentRequestForm()

    return render(request, 'patient_portal/request_appointment.html', {
        'patient': patient,
        'form': form,
    })


@patient_required
def patient_edit_appointment_request(request, pk):
    patient = request.user.patient_profile
    appt_request = get_object_or_404(
        AppointmentRequest, pk=pk, patient=patient, status='pending'
    )

    if request.method == 'POST':
        form = AppointmentRequestForm(request.POST, instance=appt_request)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your appointment request has been updated.')
            return redirect('patient_appointments')
    else:
        form = AppointmentRequestForm(instance=appt_request)

    return render(request, 'patient_portal/request_appointment.html', {
        'patient': patient,
        'form': form,
        'editing': True,
        'appt_request': appt_request,
    })


@patient_required
def patient_cancel_appointment_request(request, pk):
    patient = request.user.patient_profile
    appt_request = get_object_or_404(
        AppointmentRequest, pk=pk, patient=patient, status='pending'
    )
    if request.method == 'POST':
        appt_request.delete()
        messages.info(request, 'Your appointment request has been cancelled.')
    return redirect('patient_appointments')


@patient_required
def patient_records(request):
    patient = request.user.patient_profile

    treatment_records = patient.treatment_records.order_by('-date')
    treatment_plans = patient.treatment_plans.order_by('-created_date')

    return render(request, 'patient_portal/records.html', {
        'patient': patient,
        'treatment_records': treatment_records,
        'treatment_plans': treatment_plans,
    })


@patient_required
def patient_invoices(request):
    patient = request.user.patient_profile

    invoices = patient.invoices.prefetch_related('payments').order_by('-date_issued')
    total_balance = sum(inv.balance_due() for inv in invoices if inv.balance_due() > 0)

    return render(request, 'patient_portal/invoices.html', {
        'patient': patient,
        'invoices': invoices,
        'total_balance': total_balance,
    })


@patient_required
def patient_profile(request):
    patient = request.user.patient_profile

    if request.method == 'POST':
        form = PatientProfileForm(request.POST, instance=patient)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated.')
            return redirect('patient_profile')
    else:
        form = PatientProfileForm(instance=patient)

    return render(request, 'patient_portal/profile.html', {
        'patient': patient,
        'form': form,
    })


def accept_invite(request, token):
    try:
        invite = PatientInvite.objects.select_related('patient').get(token=token)
    except PatientInvite.DoesNotExist:
        return render(request, 'patient_portal/invite_invalid.html', {'reason': 'not_found'})

    if not invite.is_valid():
        return render(request, 'patient_portal/invite_invalid.html', {
            'reason': 'used' if invite.used else 'expired'
        })

    user = invite.patient.user
    if not user:
        return render(request, 'patient_portal/invite_invalid.html', {'reason': 'not_found'})

    if request.method == 'POST':
        form = InviteSetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            user.is_active = True
            user.save()

            patient_group, _ = Group.objects.get_or_create(name='Patient')
            user.groups.add(patient_group)

            invite.used = True
            invite.save()

            auth_login(request, user)
            messages.success(request, f'Welcome, {user.first_name}! Your patient portal is ready.')
            return redirect('patient_dashboard')
    else:
        form = InviteSetPasswordForm(user)

    return render(request, 'patient_portal/invite.html', {
        'form': form,
        'patient': invite.patient,
    })
