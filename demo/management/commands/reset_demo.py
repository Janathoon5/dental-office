from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from demo.data import reset_demo_practice


class Command(BaseCommand):
    help = 'Wipe all patient data and reload the fictional demo practice. Only runs when DEMO_MODE is on.'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='Run even with DEMO_MODE off (local development only: deletes every patient).')

    def handle(self, *args, **options):
        if not settings.DEMO_MODE and not options['force']:
            raise CommandError('DEMO_MODE is off, so this looks like a real practice. Refusing to delete patient '
                               'data. Use --force only on a local test database.')
        result = reset_demo_practice()
        self.stdout.write(self.style.SUCCESS(f"Demo practice loaded: {result['patients']} patients."))
