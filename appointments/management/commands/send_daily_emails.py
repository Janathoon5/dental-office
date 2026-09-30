import io
import logging

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from appointments.models import ScheduledJobRun

logger = logging.getLogger(__name__)

# (label, command, options). Each command already skips anyone it has
# emailed, so running this more than once a day never sends duplicates.
JOBS = [
    ('Appointment reminders', 'send_reminders', {'days': 1}),
    ('Cleaning recalls', 'send_recall_reminders', {}),
]


class Command(BaseCommand):
    help = 'Send all daily patient emails (appointment reminders and cleaning recalls). Run once a day by a scheduler.'

    def handle(self, *args, **options):
        lines, ok = [], True
        for label, command, kwargs in JOBS:
            try:
                # Both commands return "sent,skipped,no_email,failed".
                counts = call_command(command, stdout=io.StringIO(), **kwargs)
                sent, skipped, no_email, failed = (int(n) for n in counts.split(','))
                lines.append(f'{label}: {sent} sent, {skipped} already sent, '
                             f'{no_email} without an email address, {failed} failed')
            except Exception as e:
                # Keep going so one broken job doesn't block the other.
                ok = False
                logger.exception('Daily email job %s failed', command)
                lines.append(f'{label}: FAILED ({e})')

        summary = '\n'.join(lines)
        ScheduledJobRun.objects.create(succeeded=ok, summary=summary)
        self.stdout.write(summary)
        if not ok:
            # Non-zero exit so the scheduler marks the run as failed.
            raise CommandError('One or more daily email jobs failed.')
