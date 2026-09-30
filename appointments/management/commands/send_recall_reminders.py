from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone
from django.conf import settings
import datetime
from appointments.models import RecallNotice
from appointments.recalls import recall_lists


class Command(BaseCommand):
    help = 'Email patients who are due (or overdue) for their cleaning/checkup'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days-ahead', type=int, default=14,
            help='Also email patients whose recall is due within this many days (default: 14)'
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        cutoff = today + datetime.timedelta(days=options['days_ahead'])
        lists = recall_lists(today)
        candidates = lists['overdue'] + [i for i in lists['due_soon'] if i['due_date'] <= cutoff]

        sent = skipped = failed = no_email = 0

        for item in candidates:
            patient, due = item['patient'], item['due_date']

            # One email per recall cycle — the due date identifies the cycle.
            if RecallNotice.objects.filter(patient=patient, due_date=due, status='sent').exists():
                skipped += 1
                continue

            if not patient.email:
                no_email += 1
                self.stdout.write(f"  No email on file: {patient}")
                continue

            if due <= today:
                subject = "It's time for your dental cleaning"
                opener = "Our records show you're due for your regular cleaning and checkup."
            else:
                subject = "Your next dental cleaning is coming up"
                opener = (f"You're due for your next cleaning and checkup around "
                          f"{due.strftime('%B %d, %Y')}.")
            message = (
                f"Hi {patient.first_name},\n\n"
                f"{opener}\n\n"
                f"Regular cleanings help catch small problems before they become big ones. "
                f"Please call us or request an appointment through the patient portal "
                f"to book a time that works for you.\n\n"
                f"Thank you!"
            )

            try:
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [patient.email])
                RecallNotice.objects.create(
                    patient=patient, due_date=due, status='sent', recipient_email=patient.email,
                )
                sent += 1
                self.stdout.write(f"  Sent → {patient.email}")
            except Exception as e:
                RecallNotice.objects.create(
                    patient=patient, due_date=due, status='failed',
                    recipient_email=patient.email, error_message=str(e),
                )
                failed += 1
                self.stderr.write(f"  Failed for {patient.email}: {e}")

        self.stdout.write(self.style.SUCCESS(
            f"\nRecall emails: {sent} sent, {skipped} already sent, "
            f"{no_email} no email, {failed} failed."
        ))
        return f"{sent},{skipped},{no_email},{failed}"
