from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.identity.models import OTP


class Command(BaseCommand):
    help = 'Delete one-time codes older than a retention window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Keep rows newer than this many days (default: the OTP TTL).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be deleted without deleting it.',
        )

    def handle(self, *args, **options):
        days = options['days']
        if days is not None:
            age, window = timezone.timedelta(days=days), f'{days} day(s)'
        else:
            seconds = settings.OTP_TTL_SECONDS
            age, window = timezone.timedelta(seconds=seconds), f'{seconds}s (OTP_TTL_SECONDS)'

        stale = OTP.objects.filter(created_at__lt=timezone.now() - age)
        total = OTP.objects.count()

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(f'Dry run: {stale.count()} of {total} OTP rows are older than {window}.')
            )
            return

        count, _ = stale.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} of {total} OTP rows older than {window}.'))
