from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime
from appointments.emails import contact_line, long_date, office_name, send_patient_email, short_time
from appointments.models import Appointment, ReminderLog
from dental_office.providers import provider_name


class Command(BaseCommand):
    help = 'Send email reminders for upcoming appointments'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=1,
            help='How many days ahead to send reminders for (default: 1)'
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Send even if a reminder was already sent for this appointment'
        )

    def handle(self, *args, **options):
        days_ahead = options['days']
        force = options['force']
        target_date = timezone.localdate() + datetime.timedelta(days=days_ahead)

        appointments = Appointment.objects.filter(
            date=target_date,
            status='scheduled',
        ).select_related('patient', 'dentist')

        sent = skipped = failed = no_email = 0

        for appt in appointments:
            # Skip if already reminded for this appointment (unless --force)
            if not force and ReminderLog.objects.filter(
                appointment=appt, status='sent', days_before=days_ahead
            ).exists():
                skipped += 1
                self.stdout.write(f"  Skipped (already sent): {appt.patient}")
                continue

            if not appt.patient.email:
                ReminderLog.objects.create(
                    appointment=appt, status='no_email', days_before=days_ahead
                )
                no_email += 1
                self.stdout.write(f"  No email on file: {appt.patient}")
                continue

            when = f"{appt.date:%A}, {appt.date:%B} {appt.date.day} at {short_time(appt.start_time)}"
            subject = f"Appointment reminder: {when}"
            message = (
                f"Hi {appt.patient.first_name},\n\n"
                f"This is a reminder of your upcoming appointment at {office_name()}:\n\n"
                f"  Date:      {long_date(appt.date)}\n"
                f"  Time:      {short_time(appt.start_time)}\n"
            )
            if appt.dentist:
                message += f"  Provider:  {provider_name(appt.dentist)}\n"
            message += f"\nIf you need to reschedule, {contact_line()}.\n\nSee you soon!"

            try:
                send_patient_email(subject, message, appt.patient.email, patient=appt.patient)
                ReminderLog.objects.create(
                    appointment=appt,
                    status='sent',
                    recipient_email=appt.patient.email,
                    days_before=days_ahead,
                )
                sent += 1
                self.stdout.write(f"  Sent → {appt.patient.email}")
            except Exception as e:
                ReminderLog.objects.create(
                    appointment=appt,
                    status='failed',
                    recipient_email=appt.patient.email,
                    days_before=days_ahead,
                    error_message=str(e),
                )
                failed += 1
                self.stderr.write(f"  Failed for {appt.patient.email}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"\nReminders for {target_date}: {sent} sent, {skipped} skipped, "
            f"{no_email} no email, {failed} failed."
        ))
        return f"{sent},{skipped},{no_email},{failed}"
