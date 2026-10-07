from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.academic.models import Chapter, Subject, Topic
from apps.academic.services import seed_curriculum
from apps.demo.hsc_ict import CHAPTERS, SUBJECT_SLUG
from apps.question.models import Question, QuestionOption

QUESTIONS = sum(len(chapter["questions"]) for chapter in CHAPTERS)


def seed():
    call_command("seed_hsc_ict", stdout=StringIO())


class SeedHscIctTests(TestCase):
    def setUp(self):
        seed_curriculum()
        self.subject = Subject.objects.get(slug=SUBJECT_SLUG)

    def test_it_writes_the_chapters_topics_and_questions(self):
        seed()
        chapters = list(self.subject.chapters.order_by("chapter_number"))
        self.assertEqual([c.name for c in chapters], [c["name"] for c in CHAPTERS])
        self.assertEqual(
            Topic.objects.filter(chapter__subject=self.subject).count(), sum(len(c["topics"]) for c in CHAPTERS)
        )
        self.assertEqual(Question.objects.filter(block__chapter__subject=self.subject).count(), QUESTIONS)
        self.assertTrue(all(c.question_count == 20 for c in chapters))

    def test_each_question_keeps_its_answer_after_the_shuffle(self):
        seed()
        written = {prompt: choices[answer] for c in CHAPTERS for _topic, prompt, choices, answer, _ in c["questions"]}
        keyed = QuestionOption.objects.filter(is_correct=True).select_related("question")
        self.assertEqual({o.question.prompt_content: o.content for o in keyed}, written)

    def test_the_key_is_not_always_the_first_option(self):
        seed()
        positions = set(QuestionOption.objects.filter(is_correct=True).values_list("position", flat=True))
        self.assertEqual(positions, {0, 1, 2, 3})

    def test_running_it_again_adds_nothing(self):
        seed()
        seed()
        self.assertEqual(Question.objects.count(), QUESTIONS)
        self.assertEqual(Chapter.objects.filter(subject=self.subject).count(), len(CHAPTERS))

    def test_it_needs_the_curriculum(self):
        self.subject.delete()
        with self.assertRaises(CommandError):
            seed()
