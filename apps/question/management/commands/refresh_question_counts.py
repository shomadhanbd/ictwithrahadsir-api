from django.core.management.base import BaseCommand

from apps.question.services import refresh_curriculum_question_counts


class Command(BaseCommand):
    help = "Recount question counts on the curriculum, and each class's subjects and each subject's chapters."

    def handle(self, *args, **options):
        refresh_curriculum_question_counts()
        self.stdout.write(self.style.SUCCESS("Question counts refreshed."))
