"""Delete OTP rows that can no longer be used.

Nothing ever removed them, so the table grows by one row per login attempt
forever -- and every one of those rows holds a phone number next to a code
that was texted to it. They are useless the moment they are consumed or
expire, so keeping them is pure liability.

Run it on a schedule:

    python manage.py purge_expired_otps            # older than the TTL
    python manage.py purge_expired_otps --days 7   # keep a week for support
    python manage.py purge_expired_otps --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import OTP


class Command(BaseCommand):
    help = 'Delete consumed and expired one-time codes.'

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
        if options['days'] is not None:
            cutoff = timezone.now() - timezone.timedelta(days=options['days'])
            window = f"{options['days']} day(s)"
        else:
            cutoff = timezone.now() - timezone.timedelta(
                seconds=settings.OTP_TTL_SECONDS
            )
            window = f'{settings.OTP_TTL_SECONDS}s (OTP_TTL_SECONDS)'

        stale = OTP.objects.filter(created_at__lt=cutoff)
        count = stale.count()
        total = OTP.objects.count()

        if options['dry_run']:
            self.stdout.write(
                self.style.WARNING(
                    f'Dry run: {count} of {total} OTP rows are older than {window}.'
                )
            )
            return

        stale.delete()
        self.stdout.write(
            self.style.SUCCESS(f'Deleted {count} of {total} OTP rows older than {window}.')
        )
