from django.core.management.base import BaseCommand

from apps.courses.services import send_expiry_reminders


class Command(BaseCommand):
    help = "Texts students whose course access ends within EXPIRY_REMINDER_DAYS. Run daily from cron."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, help="Override EXPIRY_REMINDER_DAYS.")
        parser.add_argument("--dry-run", action="store_true", help="Count who would be texted; send nothing.")

    def handle(self, *args, days=None, dry_run=False, **options):
        count = send_expiry_reminders(days=days, dry_run=dry_run)
        verb = "would be reminded" if dry_run else "reminded"
        self.stdout.write(f"{count} student(s) {verb}.")
