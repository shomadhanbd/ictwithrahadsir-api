"""Who owns a question, its slugs, and the order rows come back in."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet
from apps.question.tests.base import BLOCKS_URL, QuestionTestCase


class OwnershipTests(QuestionTestCase):
    """A question belongs to a block or a set -- never both, never neither."""

    def test_a_standalone_question_hangs_off_its_block(self):
        block = self.block()
        question = Question.objects.create(block=block, prompt_content="2 + 2 = ?")

        block.refresh_from_db()
        self.assertEqual(block.standalone_question, question)

    def test_a_question_cannot_have_both_owners(self):
        block = self.block(kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="…")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Question.objects.create(block=block, question_set=question_set, prompt_content="x")

    def test_a_question_cannot_be_orphaned(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Question.objects.create(prompt_content="x")

    def test_clean_reports_it_before_the_database_has_to(self):
        with self.assertRaises(ValidationError):
            Question(prompt_content="x").clean()


class SlugTests(QuestionTestCase):
    def test_every_row_is_slugged_from_its_pk(self):
        block = self.block(kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="…")
        question = Question.objects.create(question_set=question_set, prompt_content="?")

        self.assertEqual(block.slug, f"b-{block.pk}")
        self.assertEqual(question_set.slug, f"qs-{question_set.pk}")
        self.assertEqual(question.slug, f"q-{question.pk}")

    def test_an_explicit_slug_is_kept(self):
        block = self.block(slug="custom")
        self.assertEqual(block.slug, "custom")


class OrderingTests(QuestionTestCase):
    def test_a_group_returns_its_questions_in_order(self):
        """The parts of a creative question come back in order."""
        block = self.block(kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="উদ্দীপক")
        for order, label in reversed(list(enumerate(["ক", "খ", "গ", "ঘ"]))):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.CQ,
                label=label,
                order_in_set=order,
                prompt_content=f"part {label}",
            )

        labels = list(question_set.questions.values_list("label", flat=True))

        self.assertEqual(labels, ["ক", "খ", "গ", "ঘ"])

    def test_the_feed_orders_blocks_with_null_chapters_last(self):
        """`chapter` is nullable and where NULLs sort is backend-dependent."""
        loose = self.block(chapter=None, order_in_chapter=0)
        placed = self.block(order_in_chapter=1)

        rows = self.client.get(BLOCKS_URL, **self.auth).json()["data"]

        self.assertEqual([row["id"] for row in rows], [placed.pk, loose.pk])

    def test_options_come_back_in_position_order(self):
        question = Question.objects.create(block=self.block(), prompt_content="?")
        for position in (2, 0, 1):
            QuestionOption.objects.create(question=question, content=str(position), position=position)

        self.assertEqual([o.position for o in question.options.all()], [0, 1, 2])

    def test_two_options_cannot_share_a_position(self):
        question = Question.objects.create(block=self.block(), prompt_content="?")
        QuestionOption.objects.create(question=question, content="a", position=0)

        with self.assertRaises(IntegrityError), transaction.atomic():
            QuestionOption.objects.create(question=question, content="b", position=0)
