"""One request saves a block with its parts; a refused part leaves nothing half-saved."""

from django.urls import reverse

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.question.models import Question, QuestionBlock, QuestionOption
from apps.question.tests.base import QuestionTestCase

SAVE_URL = reverse("api:question:admin_question_block_save")


def mcq(prompt="2 + 2 = ?", **extra):
    return {
        "question_type": "mcq",
        "prompt_content": prompt,
        "options": [
            {"content": "4", "is_correct": True, "position": 0},
            {"content": "5", "is_correct": False, "position": 1},
        ],
        **extra,
    }


class BlockSaveTests(QuestionTestCase):
    def save(self, **body):
        return self.client.post(SAVE_URL, body, content_type="application/json", **self.auth)

    def test_a_group_block_and_its_parts_are_created_together(self):
        block = {"subject_id": self.ict.pk, "kind": "group", "question_set": {"stimulus_content": "উদ্দীপক"}}
        response = self.save(block=block, questions=[mcq("first", order_in_set=0), mcq("second", order_in_set=1)])

        self.assertEqual(response.status_code, 200, response.content)
        created = QuestionBlock.objects.get(pk=response.json()["id"])
        self.assertEqual(
            list(Question.objects.filter(question_set__block=created).values_list("prompt_content", flat=True)),
            ["first", "second"],
        )

    def test_an_edit_and_a_removal_happen_in_the_same_request(self):
        response = self.save(
            block={"subject_id": self.ict.pk, "kind": "group", "question_set": {"stimulus_content": "x"}},
            questions=[mcq("kept", order_in_set=0), mcq("gone", order_in_set=1)],
        )
        group = QuestionBlock.objects.get(pk=response.json()["id"])
        kept, gone = Question.objects.filter(question_set__block=group).order_by("order_in_set")

        response = self.save(
            block_id=group.pk,
            block={"is_active": True},
            questions=[{"id": kept.pk, "prompt_content": "kept, reworded"}],
            removed_question_ids=[gone.pk],
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(Question.objects.get(pk=kept.pk).prompt_content, "kept, reworded")
        self.assertFalse(Question.objects.filter(pk=gone.pk).exists())

    def test_a_refused_part_leaves_the_block_unchanged(self):
        """The old dialog saved the block, then hit the refusal: the block change stayed."""
        standalone = self.block()
        question = Question.objects.create(block=standalone, question_type=Question.Type.MCQ, prompt_content="?")
        for position, correct in ((0, True), (1, False)):
            QuestionOption.objects.create(
                question=question, content=f"o{position}", position=position, is_correct=correct
            )
        exam = Exam.objects.create(title="Live")
        section = ExamSection.objects.create(exam=exam, title="MCQ", subject=self.ict, marks=1)
        ExamSectionQuestion.objects.create(section=section, block=standalone, marks=1)
        Exam.objects.filter(pk=exam.pk).update(status=Exam.Status.PUBLISHED)

        # Rewording is fine, but dropping an option on a published paper is refused.
        response = self.save(
            block_id=standalone.pk,
            block={"is_active": False},
            questions=[{"id": question.pk, "options": [{"content": "only", "is_correct": True, "position": 0}]}],
        )

        self.assertEqual(response.status_code, 422)
        self.assertTrue(any("Part 1" in message for message in sum(response.json()["errors"].values(), [])))
        self.assertTrue(QuestionBlock.objects.get(pk=standalone.pk).is_active)
        self.assertEqual(question.options.count(), 2)

    def test_a_part_of_another_block_cannot_be_edited_through_this_one(self):
        mine, theirs = self.block(), self.block()
        foreign = Question.objects.create(block=theirs, question_type=Question.Type.CQ, prompt_content="theirs")
        response = self.save(block_id=mine.pk, block={}, questions=[{"id": foreign.pk, "prompt_content": "hijacked"}])
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Question.objects.get(pk=foreign.pk).prompt_content, "theirs")
