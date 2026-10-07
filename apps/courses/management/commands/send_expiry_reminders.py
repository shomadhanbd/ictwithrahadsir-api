from django.core.management.base import BaseCommand

from apps.courses.services import send_access_ended_notices, send_expiry_reminders


class Command(BaseCommand):
    help = (
        "Texts students whose course access ends within EXPIRY_REMINDER_DAYS, or has just ended. Run daily from cron."
    )

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, help="Override EXPIRY_REMINDER_DAYS.")
        parser.add_argument("--dry-run", action="store_true", help="Count who would be texted; send nothing.")

    def handle(self, *args, days=None, dry_run=False, **options):
        count = send_expiry_reminders(days=days, dry_run=dry_run)
        ended = send_access_ended_notices(dry_run=dry_run)
        verb = "would be" if dry_run else "were"
        self.stdout.write(f"{count} student(s) {verb} reminded; {ended} {verb} told their access ended.")
