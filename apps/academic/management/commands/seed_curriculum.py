from django.core.management.base import BaseCommand

from apps.academic.services import seed_curriculum


class Command(BaseCommand):
    help = "Add the board curriculum (SSC and HSC, their groups and subjects); safe to run again."

    def handle(self, *args, **options):
        created = seed_curriculum()
        for label, count in created.items():
            self.stdout.write(f"  {count:>3}  {label} added")
        self.stdout.write(self.style.SUCCESS("Curriculum ready."))
