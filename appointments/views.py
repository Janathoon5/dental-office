from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
import datetime
import io
import logging
import re
from dental_office.providers import provider_name
from dental_office.roles import staff_required
from patients.forms import NewPatientForm
from patients.models import Patient
from .emails import contact_line, long_date, office_name, send_patient_email, short_time
from .models import Appointment, AppointmentRequest, ReminderLog, ScheduledJobRun
from .forms import AppointmentForm, AppointmentRequestForm
from .recalls import recall_lists, DUE_SOON_DAYS

logger = logging.getLogger(__name__)


@staff_required
def appointment_list(request):
    date_str = request.GET.get('date')
    if date_str:
        try:
            selected_date = datetime.date.fromisoformat(date_str)
        except ValueError:
            selected_date = timezone.localdate()
    else:
        selected_date = timezone.localdate()

    appointments = Appointment.objects.filter(date=selected_date).select_related('patient', 'dentist')
    prev_date = selected_date - datetime.timedelta(days=1)
    next_date = selected_date + datetime.timedelta(days=1)

    return render(request, 'appointments/appointment_list.html', {
        'appointments': appointments,
        'selected_date': selected_date,
        'prev_date': prev_date,
        'next_date': next_date,
    })


@staff_required
def appointment_detail(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    return render(request, 'appointments/appointment_detail.html', {'appointment': appointment})


@staff_required
def appointment_add(request):
    initial = {}
    patient_id = request.GET.get('patient')
    date = request.GET.get('date')
    appt_type = request.GET.get('type')
    if patient_id:
        initial['patient'] = patient_id
    if date:
        initial['date'] = date
    if appt_type in dict(Appointment.TYPE_CHOICES):
        initial['appointment_type'] = appt_type

    if request.method == 'POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appt = form.save()
            return redirect('appointment_detail', pk=appt.pk)
    else:
        form = AppointmentForm(initial=initial)
    return render(request, 'appointments/appointment_form.html', {'form': form, 'title': 'Book Appointment'})


@staff_required
def appointment_edit(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        form = AppointmentForm(request.POST, instance=appointment)
        if form.is_valid():
            form.save()
            return redirect('appointment_detail', pk=appointment.pk)
    else:
        form = AppointmentForm(instance=appointment)
    return render(request, 'appointments/appointment_form.html', {
        'form': form,
        'title': 'Edit Appointment',
        'appointment': appointment,
    })


@staff_required
def appointment_cancel(request, pk):
    appointment = get_object_or_404(Appointment, pk=pk)
    if request.method == 'POST':
        appointment.status = 'cancelled'
        appointment.save()
        return redirect('appointment_list')
    return render(request, 'appointments/appointment_confirm_cancel.html', {'appointment': appointment})


@ratelimit(key='ip', rate='10/m', block=True)
def appointment_request(request):
    if request.method == 'POST':
        form = AppointmentRequestForm(request.POST)
        if form.is_valid():
            form.save()
            return render(request, 'appointments/request_success.html')
    else:
        form = AppointmentRequestForm()
    return render(request, 'appointments/appointment_request.html', {
        'form': form,
        'today': timezone.localdate(),
    })


@staff_required
def request_list(request):
    AppointmentRequest.objects.expire_stale()
    requests = AppointmentRequest.objects.select_related("appointment")
    return render(request, 'appointments/request_list.html', {'requests': requests})


@staff_required
def request_update(request, pk):
    # Approving goes through request_book, which books the visit too.
    appt_request = get_object_or_404(AppointmentRequest, pk=pk)
    if request.method == 'POST' and request.POST.get('status') == 'declined':
        appt_request.status = 'declined'
        appt_request.save()
    return redirect('request_list')


def _digits(phone):
    return re.sub(r'\D', '', phone or '')[-10:]


def _matching_patients(appt_request):
    """Existing patients this request could belong to, best match first,
    and whether the best one is a confident match (linked portal account,
    same email or same phone) rather than just the same name."""
    if appt_request.patient_id and appt_request.patient.is_active:
        return [appt_request.patient], True
    strong = []
    if appt_request.email:
        strong += Patient.objects.filter(email__iexact=appt_request.email)[:5]
    phone = _digits(appt_request.phone)
    if len(phone) >= 7:
        strong += [p for p in Patient.objects.only('id', 'phone') if _digits(p.phone) == phone][:5]
    by_name = Patient.objects.filter(first_name__iexact=appt_request.first_name.strip(),
                                     last_name__iexact=appt_request.last_name.strip())[:5]
    seen, matches = set(), []
    for patient in [*strong, *by_name]:
        if patient.pk not in seen:
            seen.add(patient.pk)
            matches.append(Patient.objects.get(pk=patient.pk))
    return matches, bool(strong)


def _send_booking_confirmation(appointment, appt_request):
    """Email the patient their confirmed time. Returns the address it went
    to, None if there's no address, or False if sending failed."""
    to = appt_request.email or appointment.patient.email
    if not to:
        return None
    body = (
        f"Hi {appointment.patient.first_name},\n\n"
        f"Your appointment request is confirmed. We look forward to seeing you!\n\n"
        f"  Date:      {long_date(appointment.date)}\n"
        f"  Time:      {short_time(appointment.start_time)}\n"
        f"  Visit:     {appointment.get_appointment_type_display()}\n"
    )
    if appointment.dentist:
        body += f"  Provider:  {provider_name(appointment.dentist)}\n"
    body += f"\nIf you need to change or cancel it, {contact_line()}."
    try:
        send_patient_email(f'Your appointment at {office_name()} is confirmed', body, to,
                           patient=appointment.patient)
    except Exception:
        logger.exception('Booking confirmation email failed for appointment %s', appointment.pk)
        return False
    return to


@staff_required
def request_book(request, pk):
    """Approve a request by booking it: pick the patient (or add them),
    adjust the suggested time, and email the patient a confirmation."""
    appt_request = get_object_or_404(AppointmentRequest, pk=pk)
    if appt_request.status != 'pending':
        messages.info(request, f'This request is already {appt_request.get_status_display().lower()}.')
        return redirect('request_list')

    matches, confident = _matching_patients(appt_request)
    new_initial = {'first_name': appt_request.first_name, 'last_name': appt_request.last_name,
                   'phone': appt_request.phone, 'email': appt_request.email}
    if request.method == 'POST':
        choice = request.POST.get('patient_choice', 'new')
        patient = next((p for p in matches if str(p.pk) == choice), None)
        new_form = NewPatientForm(request.POST, prefix='new') if choice == 'new' else None
        form = AppointmentForm(request.POST)
        form.fields['patient'].required = False
        patient_ok = new_form.is_valid() if new_form else patient is not None
        if form.is_valid() and patient_ok:
            with transaction.atomic():
                if new_form:
                    patient = new_form.save()
                appointment = form.save(commit=False)
                appointment.patient = patient
                appointment.save()
                appt_request.status, appt_request.patient, appt_request.appointment = 'approved', patient, appointment
                appt_request.save()
            booked = (f'Booked {patient.full_name()} for {appointment.date:%A}, {appointment.date:%B} '
                      f'{appointment.date.day} at {short_time(appointment.start_time)}.')
            emailed = _send_booking_confirmation(appointment, appt_request)
            if emailed:
                messages.success(request, f'{booked} A confirmation email was sent to {emailed}.')
            elif emailed is None:
                messages.success(request, f"{booked} There's no email address on file, so let them know by phone.")
            else:
                messages.warning(request, f"{booked} The confirmation email couldn't be sent, so let them know by phone.")
            return redirect('appointment_detail', pk=appointment.pk)
        if new_form is None:
            new_form = NewPatientForm(prefix='new', initial=new_initial)
    else:
        choice = str(matches[0].pk) if matches and confident else 'new'
        new_form = NewPatientForm(prefix='new', initial=new_initial)
        form = AppointmentForm(initial={
            'date': appt_request.preferred_date, 'start_time': appt_request.preferred_time,
            'appointment_type': appt_request.appointment_type, 'status': 'scheduled',
            'notes': appt_request.message,
        })
    return render(request, 'appointments/request_book.html', {
        'appt_request': appt_request, 'form': form, 'new_form': new_form,
        'matches': matches, 'choice': choice,
    })


@staff_required
def reminders_dashboard(request):
    today = timezone.localdate()

    # Build upcoming appointment list for the next 7 days with reminder status
    upcoming = []
    for days in range(1, 8):
        day = today + datetime.timedelta(days=days)
        appts = Appointment.objects.filter(date=day, status='scheduled').select_related('patient')
        for appt in appts:
            already_sent = ReminderLog.objects.filter(
                appointment=appt, status='sent', days_before__lte=days
            ).exists()
            upcoming.append({
                'appointment': appt,
                'days_away': days,
                'reminded': already_sent,
                'has_email': bool(appt.patient.email),
            })

    recent_logs = ReminderLog.objects.select_related(
        'appointment__patient'
    ).order_by('-sent_at')[:30]

    return render(request, 'appointments/reminders.html', {
        'auto_emails': ScheduledJobRun.status(),
        'upcoming': upcoming,
        'recent_logs': recent_logs,
        'today': today,
    })


@staff_required
def send_reminders_now(request):
    if request.method == 'POST':
        try:
            days = int(request.POST.get('days', 1))
        except ValueError:
            days = 1
        force = request.POST.get('force') == '1'
        try:
            counts = call_command('send_reminders', days=days, force=force, stdout=io.StringIO())
            _report_email_counts(request, counts, 'reminder')
        except Exception as e:
            messages.error(request, f"Error sending reminders: {e}")
    return redirect('reminders_dashboard')


def _report_email_counts(request, counts, noun):
    """Turn an email command's "sent,skipped,no_email,failed" result into a
    sentence for staff, e.g. "1 reminder sent. 3 already sent."."""
    sent, skipped, no_email, failed = (int(n) for n in counts.split(','))
    parts = [f"{sent} {noun}{'' if sent == 1 else 's'} sent"]
    if skipped:
        parts.append(f"{skipped} already sent")
    if no_email:
        parts.append(f"{no_email} skipped because there's no email address on file")
    if failed:
        parts.append(f"{failed} failed to send")
    text = '. '.join(parts) + '.'
    if not any((sent, skipped, no_email, failed)):
        text = f'No {noun}s were due.'
    (messages.warning if failed else messages.success)(request, text)


RECALL_TABS = [
    ('overdue', 'Overdue'),
    ('due_soon', f'Due in next {DUE_SOON_DAYS} days'),
    ('never', 'No cleaning on record'),
]


@staff_required
def recall_list(request):
    lists = recall_lists()
    show = request.GET.get('show')
    if show not in lists:
        show = 'overdue'
    tabs = [(key, label, len(lists[key])) for key, label in RECALL_TABS]
    return render(request, 'appointments/recalls.html', {
        'auto_emails': ScheduledJobRun.status(),
        'items': lists[show],
        'show': show,
        'tabs': tabs,
    })


@staff_required
def send_recalls_now(request):
    if request.method == 'POST':
        try:
            counts = call_command('send_recall_reminders', stdout=io.StringIO())
            _report_email_counts(request, counts, 'recall email')
        except Exception as e:
            messages.error(request, f"Error sending recall emails: {e}")
    return redirect('recall_list')
