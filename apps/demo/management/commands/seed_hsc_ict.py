from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.demo.hsc_ict import SUBJECT_SLUG
from apps.demo.hsc_ict_seed import seed_hsc_ict


class Command(BaseCommand):
    help = "Add HSC ICT's six chapters, their topics and 20 MCQs each; safe to run again (seed_demo runs it too)."

    @transaction.atomic
    def handle(self, *args, **options):
        if not seed_hsc_ict(self.stdout.write):
            raise CommandError(f"No subject “{SUBJECT_SLUG}”; run `manage.py seed_curriculum` first.")
        self.stdout.write(self.style.SUCCESS("HSC ICT ready."))
