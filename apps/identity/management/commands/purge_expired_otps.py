from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.identity.models import OTP

OTP_RATE_WINDOW_SECONDS = 3600  # the window `seconds_until_resend` caps sends over


class Command(BaseCommand):
    help = 'Delete one-time codes older than a retention window.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=None,
            help='Keep rows newer than this many days; never less than one hour (or the OTP TTL if longer).',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would be deleted without deleting it.',
        )

    def handle(self, *args, **options):
        # The hourly per-phone cap counts the last hour's rows, so no window may be shorter than that.
        floor = timezone.timedelta(seconds=max(settings.OTP_TTL_SECONDS, OTP_RATE_WINDOW_SECONDS))
        days = options['days']
        age = max(timezone.timedelta(days=days), floor) if days is not None else floor
        window = f'{int(age.total_seconds())}s'

        stale = OTP.objects.older_than(timezone.now() - age)
        total = OTP.objects.count()

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(f'Dry run: {stale.count()} of {total} OTP rows are older than {window}.')
            )
            return

        count, _ = stale.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} of {total} OTP rows older than {window}.'))
