"""Hygiene recall tracking: works out when each patient is next due for a
cleaning/checkup, based on their last completed one and their recall
interval. Nothing is stored — it's recomputed from appointments each time,
so it can never drift out of sync with the schedule."""
import calendar
import datetime

from django.db.models import Exists, Max, OuterRef, Q
from django.utils import timezone

from patients.models import Patient
from .models import Appointment, RecallNotice

HYGIENE_TYPES = ('cleaning', 'checkup')
DUE_SOON_DAYS = 30


def add_months(date, months):
    month_index = date.month - 1 + months
    year = date.year + month_index // 12
    month = month_index % 12 + 1
    # Clamp e.g. Aug 31 + 6 months to Feb 28/29 instead of crashing.
    day = min(date.day, calendar.monthrange(year, month)[1])
    return datetime.date(year, month, day)


def patients_with_recall_info(today=None):
    """Every active patient annotated with `last_hygiene` (date of their last
    completed cleaning/checkup, or None) and `has_upcoming_hygiene` (a
    cleaning/checkup is already booked)."""
    today = today or timezone.localdate()
    upcoming = Appointment.objects.filter(
        patient=OuterRef('pk'), status='scheduled',
        appointment_type__in=HYGIENE_TYPES, date__gte=today,
    )
    return Patient.objects.annotate(
        last_hygiene=Max(
            'appointments__date',
            filter=Q(appointments__status='completed',
                     appointments__appointment_type__in=HYGIENE_TYPES),
        ),
        has_upcoming_hygiene=Exists(upcoming),
    )


def recall_due_date(patient):
    """Needs a patient from patients_with_recall_info()."""
    if patient.last_hygiene is None:
        return None
    return add_months(patient.last_hygiene, patient.recall_interval_months)


def recall_for_patient(patient, today=None):
    """Recall summary for a single patient (used on the patient detail page)."""
    today = today or timezone.localdate()
    annotated = patients_with_recall_info(today).get(pk=patient.pk)
    due = recall_due_date(annotated)
    return {
        'last_hygiene': annotated.last_hygiene,
        'due_date': due,
        'is_booked': annotated.has_upcoming_hygiene,
        'is_overdue': due is not None and due <= today and not annotated.has_upcoming_hygiene,
    }


def recall_lists(today=None):
    """Patients who need to be called in, split into three groups. Anyone who
    already has a cleaning/checkup booked is left out — they're handled."""
    today = today or timezone.localdate()
    soon_cutoff = today + datetime.timedelta(days=DUE_SOON_DAYS)

    patients = list(patients_with_recall_info(today).filter(has_upcoming_hygiene=False))
    last_notice = {}
    for notice in RecallNotice.objects.filter(
        patient__in=patients, status='sent'
    ).order_by('sent_at'):
        last_notice[notice.patient_id] = notice

    overdue, due_soon, never = [], [], []
    for p in patients:
        due = recall_due_date(p)
        item = {
            'patient': p,
            'last_hygiene': p.last_hygiene,
            'due_date': due,
            'days_overdue': (today - due).days if due else None,
            'last_notice': last_notice.get(p.pk),
        }
        if due is None:
            never.append(item)
        elif due <= today:
            overdue.append(item)
        elif due <= soon_cutoff:
            due_soon.append(item)

    overdue.sort(key=lambda i: i['due_date'])
    due_soon.sort(key=lambda i: i['due_date'])
    never.sort(key=lambda i: (i['patient'].last_name, i['patient'].first_name))
    return {'overdue': overdue, 'due_soon': due_soon, 'never': never}
