"""Question counts on blocks and on the curriculum."""

from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from apps.academic.models import Topic
from apps.core.testing import bearer, make_user, next_slug
from apps.identity.models import User
from apps.question import services
from apps.question.models import Question, QuestionBlock, QuestionSet
from apps.question.tests.base import QUESTIONS_URL, QuestionTestCase, detail


class QuestionCountTests(QuestionTestCase):
    """`question_count` on a block is maintained on write."""

    def test_it_follows_a_standalone_question(self):
        block = self.block()

        self.client.post(
            QUESTIONS_URL,
            {
                "block_id": block.pk,
                "question_type": "cq",
                "prompt_content": "?",
            },
            content_type="application/json",
            **self.auth,
        )

        block.refresh_from_db()
        self.assertEqual(block.question_count, 1)

    def test_it_counts_every_question_of_a_group(self):
        block = self.block(kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="…")
        for order in range(3):
            self.client.post(
                QUESTIONS_URL,
                {
                    "question_set_id": question_set.pk,
                    "question_type": "cq",
                    "order_in_set": order,
                    "prompt_content": f"part {order}",
                },
                content_type="application/json",
                **self.auth,
            )

        block.refresh_from_db()
        self.assertEqual(block.question_count, 3)

    def test_it_is_recomputed_rather_than_incremented(self):
        block = self.block()
        Question.objects.create(block=block, prompt_content="?")
        block.question_count = 99
        block.save(update_fields=["question_count"])

        services.sync_question_count(block)

        block.refresh_from_db()
        self.assertEqual(block.question_count, 1)

    def test_it_drops_when_a_question_is_deleted_through_the_api(self):
        block = self.block()
        question = Question.objects.create(block=block, prompt_content="?")
        block.refresh_from_db()
        self.assertEqual(block.question_count, 1)

        self.client.delete(detail("question", question.pk), **self.auth)

        block.refresh_from_db()
        self.assertEqual(block.question_count, 0)

    def test_it_follows_a_question_written_through_the_orm(self):
        """The Django admin and the shell write here, not through the serializer."""
        block = self.block()

        question = Question.objects.create(block=block, prompt_content="?")

        block.refresh_from_db()
        self.assertEqual(block.question_count, 1)

        question.delete()

        block.refresh_from_db()
        self.assertEqual(block.question_count, 0)

    def test_a_question_that_moves_decrements_the_block_it_left(self):
        origin, destination = self.block(), self.block(order_in_chapter=1)
        question = Question.objects.create(block=origin, prompt_content="?")

        moved = Question.objects.get(pk=question.pk)
        moved.block = destination
        moved.save()

        origin.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual((origin.question_count, destination.question_count), (0, 1))

    def test_deleting_a_block_does_not_trip_over_its_own_questions(self):
        """The cascade deletes the questions before the block."""
        block = self.block()
        Question.objects.create(block=block, prompt_content="?")

        block.delete()

        self.assertFalse(QuestionBlock.objects.filter(pk=block.pk).exists())

    def test_emptying_a_group_leaves_the_block_at_zero(self):
        block = self.block(kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="…")
        Question.objects.create(question_set=question_set, prompt_content="ক")
        block.refresh_from_db()
        self.assertEqual(block.question_count, 1)

        question_set.delete()

        block.refresh_from_db()
        self.assertEqual(block.question_count, 0)


class RefreshQuestionCountTests(QuestionTestCase):
    """`question_count` on the curriculum is recounted on demand, not on write."""

    URL = reverse("api:question:admin_question_counts_refresh")

    def setUp(self):
        super().setUp()
        self.binary = Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)
        self.block().topics.add(self.binary)
        group = self.block(kind=QuestionBlock.Kind.GROUP)
        stimulus = QuestionSet.objects.create(block=group, stimulus_content="A stimulus")
        for label in ("ক", "খ"):
            Question.objects.create(
                question_set=stimulus, question_type=Question.Type.CQ, label=label, prompt_content="?"
            )

    def counts(self):
        rows = (self.hsc, self.science, self.ict, self.chapter, self.binary)
        for row in rows:
            row.refresh_from_db()
        return [row.question_count for row in rows]

    def test_adding_a_question_does_not_count_it_yet(self):
        self.assertEqual(self.counts(), [0, 0, 0, 0, 0])

    def test_the_refresh_counts_each_block_once(self):
        response = self.client.post(self.URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True})
        # Two blocks: a standalone question and a stimulus with two parts.
        self.assertEqual(self.counts(), [2, 2, 2, 2, 1])

    def test_a_retired_block_is_not_counted(self):
        QuestionBlock.objects.filter(question_set__isnull=False).update(is_active=False)
        self.client.post(self.URL, **self.auth)
        self.assertEqual(self.counts(), [1, 1, 1, 1, 1])

    def test_the_command_does_the_same(self):
        call_command("refresh_question_counts", stdout=StringIO())
        self.assertEqual(self.counts(), [2, 2, 2, 2, 1])

    def test_teaching_staff_only(self):
        teacher = make_user(role=User.Role.TEACHER, name="Teacher")
        student = make_user(name="Student")
        for user, expected in ((teacher, 200), (student, 403)):
            auth = bearer(user)
            with self.subTest(user=user.name):
                self.assertEqual(self.client.post(self.URL, **auth).status_code, expected)
