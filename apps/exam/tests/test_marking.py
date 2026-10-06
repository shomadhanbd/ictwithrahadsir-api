"""Per-section marking rules and paper shuffling."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.exam import selectors, utils
from apps.exam.models import ExamSection, ExamSectionQuestion
from apps.exam.tests.base import (
    SECTIONS_URL,
    ExamTestCase,
)


class SectionMarkingRuleTests(ExamTestCase):
    """MCQ and CQ are marked differently, and the paper says so per part."""

    def post(self, **overrides):
        payload = {
            "exam_id": self.exam().pk,
            "title": "MCQ",
            "question_type": "mcq",
            "subject_id": self.ict.pk,
            "marks": "30.00",
            "marks_per_question": "1.00",
            **overrides,
        }
        return self.client.post(SECTIONS_URL, payload, content_type="application/json", **self.auth)

    def assert_refused(self, field, **overrides):
        response = self.post(**overrides)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn(field, response.json()["errors"])

    def test_negative_marking_is_written_as_a_positive_amount(self):
        self.assert_refused("negative_marks", negative_marks="-0.25")

    def test_a_wrong_answer_cannot_cost_more_than_a_right_one_earns(self):
        self.assert_refused("negative_marks", marks_per_question="1.00", negative_marks="2.00")

    def test_a_creative_question_part_cannot_be_negatively_marked(self):
        """Nothing can detect a wrong creative answer to penalise."""
        self.assert_refused("negative_marks", question_type="cq", marks_per_question="10.00", negative_marks="1.00")

    def test_a_blank_rate_round_trips_as_null(self):
        """A blank rate stays NULL; `section_marking` reads NULL and 0 alike."""
        explicit = self.post(title="Explicit", negative_marks="0.00").json()
        blank = self.post(title="Blank").json()

        self.assertEqual(Decimal(explicit["negative_marks"]), Decimal("0.00"))
        self.assertIsNone(blank["negative_marks"])

    def test_a_creative_part_has_no_options_to_shuffle(self):
        self.assert_refused("shuffle_options", question_type="cq", marks_per_question="10.00", shuffle_options=True)

    def test_an_mcq_part_may_shuffle_its_options(self):
        response = self.post(title="Shuffled", shuffle_options=True, shuffle_questions=True)

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["shuffle_options"])
        self.assertTrue(body["shuffle_questions"])

    def test_a_creative_part_may_still_shuffle_its_questions(self):
        """Only option shuffling is MCQ-only."""
        response = self.post(
            title="CQ shuffled", question_type="cq", marks_per_question="10.00", shuffle_questions=True
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["shuffle_questions"])

    def test_a_part_cannot_be_worth_less_than_its_own_pass_mark(self):
        self.assert_refused("pass_marks", marks="30.00", pass_marks="40.00")

    def test_a_zero_pass_mark_is_refused(self):
        self.assert_refused("pass_marks", pass_marks="0.00")

    def test_the_database_refuses_negative_marking_above_the_rate(self):
        """Exercises the constraint itself; the serializer normally refuses first."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.section(marks_per_question=Decimal("1.00"), negative_marks=Decimal("2.00"))

    def test_the_database_refuses_a_pass_mark_above_the_section_marks(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.section(marks=Decimal("30.00"), pass_marks=Decimal("40.00"))

    def test_the_admin_form_path_runs_the_same_rules(self):
        """The Django admin goes through `clean()`."""
        section = ExamSection(
            exam=self.exam(),
            title="Bad",
            question_type=ExamSection.Type.CQ,
            subject=self.ict,
            marks=Decimal("10.00"),
            marks_per_question=Decimal("10.00"),
            negative_marks=Decimal("1.00"),
        )

        with self.assertRaises(ValidationError):
            section.clean()


class SectionMarkingResolutionTests(ExamTestCase):
    """Negative marking belongs to the section, not the paper."""

    def test_a_part_carries_its_own_rate(self):
        section = self.section(negative_marks=Decimal("0.25"))

        self.assertEqual(selectors.section_marking(section).negative, Decimal("0.25"))

    def test_a_part_that_sets_nothing_is_not_penalised(self):
        section = self.section()

        self.assertEqual(selectors.section_marking(section).negative, Decimal("0.00"))

    def test_an_explicit_zero_is_not_penalised_either(self):
        """NULL and 0 both subtract nothing."""
        section = self.section(negative_marks=Decimal("0.00"))

        self.assertEqual(selectors.section_marking(section).negative, Decimal("0.00"))

    def test_a_creative_part_is_never_negatively_marked(self):
        section = self.section(
            title="সৃজনশীল",
            question_type=ExamSection.Type.CQ,
            marks=70,
            marks_per_question=10,
            negative_marks=Decimal("0.25"),
        )

        self.assertEqual(selectors.section_marking(section).negative, Decimal("0.00"))

    def test_the_positive_rate_is_the_parts_own(self):
        section = self.section(marks=70, marks_per_question=Decimal("10.00"))

        self.assertEqual(selectors.section_marking(section).positive, Decimal("10.00"))

    def test_resolving_costs_no_query_when_the_exam_is_passed(self):
        exam = self.exam()
        section = self.section(exam=exam)

        with self.assertNumQueries(0):
            selectors.section_marking(section)


class PaperShuffleTests(ExamTestCase):
    """Shuffling permutes picks, and a pick is a block."""

    def setUp(self):
        super().setUp()
        self.section_row = self.section(marks=20, marks_per_question=1)
        self.picks = [
            ExamSectionQuestion.objects.create(section=self.section_row, block=self.mcq_block(), order=order)
            for order in range(6)
        ]

    def ordered(self, seed):
        picks = self.section_row.section_questions.order_by("order", "id")
        return [pick.pk for pick in utils.seeded_shuffle(picks, seed=seed)]

    def test_it_loses_nothing_and_invents_nothing(self):
        shuffled = self.ordered(utils.paper_seed(exam_id=1, user_id=7))

        self.assertCountEqual(shuffled, [pick.pk for pick in self.picks])

    def test_the_same_student_gets_the_same_paper_twice(self):
        seed = utils.paper_seed(exam_id=1, user_id=7)

        self.assertEqual(self.ordered(seed), self.ordered(seed))

    def test_a_different_student_gets_a_different_paper(self):
        mine = self.ordered(utils.paper_seed(exam_id=1, user_id=7))
        theirs = self.ordered(utils.paper_seed(exam_id=1, user_id=8))

        self.assertNotEqual(mine, theirs)

    def test_the_seed_does_not_move_between_processes(self):
        """`hash()` is salted per process; this must not be."""
        self.assertEqual(
            utils.paper_seed(exam_id=1, user_id=7),
            utils.paper_seed(exam_id=1, user_id=7),
        )
        self.assertNotEqual(
            utils.paper_seed(exam_id=1, user_id=7),
            utils.paper_seed(exam_id=2, user_id=7),
        )

    def test_a_passage_is_never_taken_apart(self):
        """The block is the unit shuffled, so a passage moves with its questions."""
        passage = self.mcq_passage(parts=3)
        ExamSectionQuestion.objects.create(section=self.section_row, block=passage, marks=3, order=6)

        shuffled = utils.seeded_shuffle(
            self.section_row.section_questions.order_by("order", "id"), seed=utils.paper_seed(exam_id=1, user_id=7)
        )

        placed = [pick for pick in shuffled if pick.block_id == passage.pk]
        self.assertEqual(len(placed), 1, "the passage was split across picks")
        self.assertEqual(
            list(passage.question_set.questions.values_list("order_in_set", flat=True)),
            [0, 1, 2],
            "the passage's own questions were reordered",
        )

    def test_options_shuffle_is_a_permutation(self):
        options = ["ক", "খ", "গ", "ঘ"]

        shuffled = utils.seeded_shuffle(options, seed=utils.paper_seed(exam_id=1, user_id=7))

        self.assertCountEqual(shuffled, options)
        self.assertIsNot(shuffled, options, "the caller's list was mutated")
