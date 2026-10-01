from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Everything the daily scheduler runs: reload the demo practice (demo mode only), then send daily emails.'

    def handle(self, *args, **options):
        if settings.DEMO_MODE:
            call_command('reset_demo', stdout=self.stdout)
        call_command('send_daily_emails', stdout=self.stdout)
