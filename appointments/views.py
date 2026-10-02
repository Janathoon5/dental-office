from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.core.management import call_command
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
import datetime
import io
from dental_office.roles import staff_required
from .models import Appointment, AppointmentRequest, ReminderLog, ScheduledJobRun
from .forms import AppointmentForm, AppointmentRequestForm
from .recalls import recall_lists, DUE_SOON_DAYS


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
    requests = AppointmentRequest.objects.all()
    return render(request, 'appointments/request_list.html', {'requests': requests})


@staff_required
def request_update(request, pk):
    appt_request = get_object_or_404(AppointmentRequest, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        if new_status in ('approved', 'declined'):
            appt_request.status = new_status
            appt_request.save()
    return redirect('request_list')


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
