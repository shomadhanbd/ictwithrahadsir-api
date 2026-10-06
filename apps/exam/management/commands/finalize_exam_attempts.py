from django.core.management.base import BaseCommand

from apps.exam.models import ExamAttempt
from apps.exam.services.attempts import finalize_expired


class Command(BaseCommand):
    help = "Submits and marks every exam attempt whose time has run out. Run every minute from cron."

    def handle(self, *args, **options):
        count = finalize_expired(ExamAttempt.objects.all())
        self.stdout.write(f"{count} attempt(s) finalized.")
