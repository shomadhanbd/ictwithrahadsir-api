"""The one-official-attempt constraint arrives with its own data fix."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

BEFORE = [("exam", "0003_course_exams")]
AFTER = [("exam", "0004_attempt_official_and_deadline")]


class OfficialAttemptMigrationTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    def tearDown(self):
        self.migrate(executor_leaf_nodes())

    def test_a_database_with_two_official_attempts_still_migrates(self):
        apps = self.migrate(BEFORE)
        User = apps.get_model("identity", "User")
        Exam = apps.get_model("exam", "Exam")
        ExamAttempt = apps.get_model("exam", "ExamAttempt")
        user = User.objects.create(phone="01810007171", name="Student")
        exam = Exam.objects.create(title="Old exam", slug="old-exam")
        now = timezone.now()
        later = ExamAttempt.objects.create(
            exam=exam, user=user, number=2, seed=1, started_at=now, submitted_at=now, is_official=True
        )
        earlier = ExamAttempt.objects.create(
            exam=exam,
            user=user,
            number=1,
            seed=1,
            started_at=now,
            submitted_at=now - timezone.timedelta(days=1),
            is_official=True,
        )

        apps = self.migrate(AFTER)

        ExamAttempt = apps.get_model("exam", "ExamAttempt")
        self.assertEqual(list(ExamAttempt.objects.filter(is_official=True).values_list("pk", flat=True)), [earlier.pk])
        self.assertFalse(ExamAttempt.objects.get(pk=later.pk).is_official)


def executor_leaf_nodes():
    executor = MigrationExecutor(connection)
    return executor.loader.graph.leaf_nodes()
