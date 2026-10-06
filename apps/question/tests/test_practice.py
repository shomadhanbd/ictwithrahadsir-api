from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.academic.models import Chapter
from apps.core.tests.base import ThrottledAPITestCase
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet
from apps.question.tests.base import QuestionTestCase

TREE_URL = reverse("api:question:practice_tree")
QUESTIONS_URL = reverse("api:question:practice_questions")


class PracticeTests(QuestionTestCase, ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        Chapter.objects.filter(pk=self.chapter.pk).update(practice_enabled=True)

    def test_a_chapter_is_not_practised_until_it_is_opened(self):
        """Questions written for an upcoming exam must not be served, with answers, to anyone."""
        Chapter.objects.filter(pk=self.chapter.pk).update(practice_enabled=False)
        self.mcq(text="next week's paper")
        self.assertEqual(self.round_ids(), set())
        self.assertEqual(self.client.get(TREE_URL).json()["data"], [])

    def mcq(self, chapter=None, *, block=None, question_set=None, correct=True, text="১ বাইট = কত বিট?"):
        if block is None and question_set is None:
            block = QuestionBlock.objects.create(subject=self.ict, chapter=chapter or self.chapter)
        question = Question.objects.create(
            block=block, question_set=question_set, question_type=Question.Type.MCQ, prompt_content=text
        )
        QuestionOption.objects.create(question=question, label="ক", content="৪", position=0, is_correct=False)
        QuestionOption.objects.create(question=question, label="খ", content="৮", position=1, is_correct=correct)
        return question

    def place_on_exam(self, question, **exam_fields):
        exam = Exam.objects.create(title="Test", **exam_fields)
        section = ExamSection.objects.create(exam=exam, title="MCQ", subject=self.ict)
        ExamSectionQuestion.objects.create(section=section, block=question.block)
        return exam

    def round_ids(self, **params):
        response = self.client.get(QUESTIONS_URL, {"chapter": self.chapter.pk, **params})
        self.assertEqual(response.status_code, 200, response.content)
        return {q["id"] for q in response.json()["data"]}

    def test_the_tree_lists_only_chapters_with_practice_questions(self):
        self.mcq()
        retired = Chapter.objects.create(
            name="Retired", subject=self.ict, chapter_number=3, is_active=False, practice_enabled=True
        )
        self.mcq(retired)
        Chapter.objects.create(name="Empty", subject=self.ict, chapter_number=4, practice_enabled=True)
        closed = Chapter.objects.create(name="Not opened", subject=self.ict, chapter_number=5)
        self.mcq(closed)

        tree = self.client.get(TREE_URL).json()["data"]
        self.assertEqual(len(tree), 1)
        chapters = tree[0]["subjects"][0]["chapters"]
        self.assertEqual([(c["name"], c["question_count"]) for c in chapters], [("Number Systems", 1)])

    def test_a_round_carries_the_key_and_explanation(self):
        question = self.mcq()
        question.explanation = "৮ বিটে ১ বাইট।"
        question.save()
        item = self.client.get(QUESTIONS_URL, {"chapter": self.chapter.pk}).json()["data"][0]
        self.assertEqual(item["select_mode"], "single")
        self.assertEqual(len(item["options"]), 2)
        self.assertEqual(item["correct_option_ids"], [question.options.get(is_correct=True).pk])
        self.assertEqual(item["explanation"], "৮ বিটে ১ বাইট।")
        self.assertIsNone(item["stimulus"])

    def test_set_questions_carry_their_stimulus(self):
        group = QuestionBlock.objects.create(subject=self.ict, chapter=self.chapter, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=group, stimulus_content="উদ্দীপক")
        self.mcq(question_set=question_set)
        item = self.client.get(QUESTIONS_URL, {"chapter": self.chapter.pk}).json()["data"][0]
        self.assertEqual(item["stimulus"]["content"], "উদ্দীপক")

    def test_only_keyed_active_mcqs_are_practised(self):
        kept = self.mcq()
        self.mcq(correct=False)
        retired = self.mcq()
        QuestionBlock.objects.filter(pk=retired.block_id).update(is_active=False)
        cq = QuestionBlock.objects.create(subject=self.ict, chapter=self.chapter)
        Question.objects.create(block=cq, question_type=Question.Type.CQ, prompt_content="CQ")
        self.assertEqual(self.round_ids(), {kept.pk})

    def test_questions_on_unreleased_papers_are_held_back(self):
        later = timezone.now() + timezone.timedelta(days=1)
        earlier = timezone.now() - timezone.timedelta(days=1)
        draft = self.mcq(text="draft")
        self.place_on_exam(draft)
        running = self.mcq(text="running")
        self.place_on_exam(running, status=Exam.Status.PUBLISHED, end_time=later)
        released = self.mcq(text="released")
        self.place_on_exam(released, status=Exam.Status.PUBLISHED, end_time=earlier)
        free = self.mcq(text="free")
        self.assertEqual(self.round_ids(), {released.pk, free.pk})

    def test_an_exam_that_never_closes_keeps_its_questions_out_of_practice(self):
        """With no end time, results are out at once, yet students can still sit the paper."""
        open_ended = self.mcq(text="self-paced")
        self.place_on_exam(open_ended, status=Exam.Status.PUBLISHED)
        result_time_only = self.mcq(text="result time only")
        self.place_on_exam(
            result_time_only,
            status=Exam.Status.PUBLISHED,
            result_publish_time=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertEqual(self.round_ids(), set())

    def test_a_round_is_capped(self):
        for _ in range(25):
            self.mcq()
        self.assertEqual(len(self.round_ids()), 10)
        self.assertEqual(len(self.round_ids(count=100)), 20)

    def test_a_round_needs_a_chapter(self):
        self.assertEqual(self.client.get(QUESTIONS_URL).status_code, 422)

    def test_queries_do_not_grow_with_the_round(self):
        for _ in range(12):
            self.mcq()
        with CaptureQueriesContext(connection) as tree_queries:
            self.client.get(TREE_URL)
        with CaptureQueriesContext(connection) as round_queries:
            self.client.get(QUESTIONS_URL, {"chapter": self.chapter.pk, "count": 12})
        self.assertLessEqual(len(tree_queries), 3)
        self.assertLessEqual(len(round_queries), 3)
