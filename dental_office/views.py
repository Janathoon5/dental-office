from django.shortcuts import render
from django.utils import timezone
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
import datetime
import json
from patients.models import Patient
from appointments.models import Appointment
from billing.models import Invoice
from dental_office.roles import staff_required, dentist_required, is_dentist


def privacy_policy(request):
    return render(request, 'privacy_policy.html', {
        'last_updated': datetime.date.today().strftime('%B %d, %Y'),
    })


@staff_required
def dashboard(request):
    today = timezone.localdate()
    todays_appointments = Appointment.objects.filter(
        date=today
    ).select_related('patient', 'dentist').order_by('start_time')

    week_start = today - datetime.timedelta(days=today.weekday())
    week_end = week_start + datetime.timedelta(days=6)

    stats = {
        'total_patients': Patient.objects.count(),
        'appointments_today': todays_appointments.count(),
        'appointments_this_week': Appointment.objects.filter(date__range=[week_start, week_end]).count(),
        'upcoming': Appointment.objects.filter(date__gt=today, status='scheduled').count(),
    }

    pending_requests = 0
    try:
        from appointments.models import AppointmentRequest
        AppointmentRequest.objects.expire_stale()
        pending_requests = AppointmentRequest.objects.filter(status='pending').count()
    except Exception:
        pass

    my_appointments_today = None
    if is_dentist(request.user):
        my_appointments_today = todays_appointments.filter(dentist=request.user).count()

    return render(request, 'dashboard.html', {
        'todays_appointments': todays_appointments,
        'today': today,
        'stats': stats,
        'pending_requests': pending_requests,
        'my_appointments_today': my_appointments_today,
    })


@dentist_required
def reports(request):
    today = timezone.localdate()
    # Last 6 months of revenue
    six_months_ago = today.replace(day=1) - datetime.timedelta(days=150)
    monthly_revenue = (
        Invoice.objects
        .filter(date_issued__gte=six_months_ago)
        .annotate(month=TruncMonth('date_issued'))
        .values('month')
        .annotate(total=Sum('subtotal'), insurance=Sum('insurance_amount'))
        .order_by('month')
    )
    revenue_labels = [r['month'].strftime('%b %Y') for r in monthly_revenue]
    revenue_totals = [float(r['total']) for r in monthly_revenue]
    revenue_insurance = [float(r['insurance']) for r in monthly_revenue]
    revenue_patient = [round(revenue_totals[i] - revenue_insurance[i], 2) for i in range(len(revenue_totals))]

    # Appointments by type (last 30 days)
    thirty_days_ago = today - datetime.timedelta(days=30)
    appt_by_type = (
        Appointment.objects
        .filter(date__gte=thirty_days_ago)
        .values('appointment_type')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    type_labels = [a['appointment_type'].title() for a in appt_by_type]
    type_counts = [a['count'] for a in appt_by_type]

    # Summary stats
    total_revenue = sum(revenue_totals)
    pending_invoices = Invoice.objects.filter(status='pending').count()
    new_patients_month = Patient.objects.filter(
        created_at__year=today.year, created_at__month=today.month
    ).count()

    return render(request, 'reports.html', {
        'revenue_labels': json.dumps(revenue_labels),
        'revenue_totals': json.dumps(revenue_totals),
        'revenue_patient': json.dumps(revenue_patient),
        'type_labels': json.dumps(type_labels),
        'type_counts': json.dumps(type_counts),
        'total_revenue': total_revenue,
        'pending_invoices': pending_invoices,
        'new_patients_month': new_patients_month,
    })
