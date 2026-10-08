"""Sections and the blocks picked onto them."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academic.models import Batch
from apps.exam import selectors, validators
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.services import sections as section_service
from apps.exam.services.sections import sync_section_totals
from apps.exam.tests.base import (
    SECTIONS_URL,
    ExamTestCase,
    block_detail,
    detail,
    section_questions,
)
from apps.question.models import Question, QuestionBlock
from apps.question.services import sync_question_count


class SectionCompositionTests(ExamTestCase):
    def post(self, exam=None, **overrides):
        payload = {
            "exam_id": (exam or self.exam()).pk,
            "title": "MCQ",
            "question_type": "mcq",
            "subject_id": self.ict.pk,
            "marks": "30.00",
            "marks_per_question": "1.00",
            **overrides,
        }
        return self.client.post(SECTIONS_URL, payload, content_type="application/json", **self.auth)

    def test_a_paper_takes_any_section_type(self):
        exam = self.exam()

        self.assertEqual(self.post(exam=exam, title="MCQ", marks="30.00").status_code, 201)
        self.assertEqual(self.post(exam=exam, title="সৃজনশীল", question_type="cq", marks="70.00").status_code, 201)

    def test_a_paper_reports_the_types_it_contains(self):
        exam = self.exam()
        self.post(exam=exam, title="MCQ", marks="30.00")
        self.post(exam=exam, title="সৃজনশীল", question_type="cq", marks="70.00")

        body = self.client.get(detail("exam", exam.pk), **self.auth).json()

        self.assertEqual(body["question_types"], ["mcq", "cq"])

    def test_the_exam_total_follows_its_sections(self):
        exam = self.exam()
        mcq = self.section(exam=exam, title="MCQ", marks=25)
        self.assertEqual(self.post(exam=exam, title="CQ", marks="40.00").status_code, 201)
        exam.refresh_from_db()
        self.assertEqual(exam.total_marks, 65)

        mcq.delete()
        exam.refresh_from_db()
        self.assertEqual(exam.total_marks, 40)

    def test_the_sections_cannot_outrun_the_exam(self):
        exam = self.exam(duration_minutes=90)
        self.section(exam=exam, title="MCQ", marks=30, duration_minutes=60)

        response = self.post(exam=exam, title="Second", marks="30.00", duration_minutes=45)

        self.assertEqual(response.status_code, 422)
        self.assertIn("duration_minutes", response.json()["errors"])

    def test_a_subject_from_another_class_level_is_refused_on_a_batch_exam(self):
        batch = Batch.objects.create(name="SSC-2027", class_level=self.ssc, slug="ssc-2027")
        exam = self.exam(scope=Exam.Scope.BATCH, batch=batch)

        response = self.post(exam=exam)

        self.assertEqual(response.status_code, 422)
        self.assertIn("subject_id", response.json()["errors"])

    def test_two_sections_of_one_exam_cannot_share_a_title(self):
        exam = self.exam()
        self.section(exam=exam, title="MCQ")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.section(exam=exam, title="MCQ")


class BlockTypeRuleTests(ExamTestCase):
    """A block has no type of its own -- it lives on its questions."""

    def add(self, section, block, auth=None):
        """Adds `block` after the section's current questions, as the picker saves the whole list."""
        kept = list(section.section_questions.order_by("order", "id").values_list("block_id", flat=True))
        return self.client.put(
            section_questions(section.pk),
            {"block_ids": [*kept, block.pk]},
            content_type="application/json",
            **(auth or self.auth),
        )

    def test_an_mcq_block_joins_an_mcq_section(self):
        self.assertEqual(self.add(self.section(), self.mcq_block()).status_code, 200)

    def test_a_creative_question_block_is_refused_by_an_mcq_section(self):
        response = self.add(self.section(), self.cq_block())

        self.assertEqual(response.status_code, 422)
        self.assertIn("block_ids", response.json()["errors"])

    def test_an_mcq_block_is_refused_by_a_creative_question_section(self):
        exam = self.exam()
        section = self.section(exam=exam, title="সৃজনশীল", question_type=ExamSection.Type.CQ, marks=70)

        self.assertEqual(self.add(section, self.mcq_block()).status_code, 422)

    def test_a_creative_question_block_joins_a_creative_question_section(self):
        exam = self.exam()
        section = self.section(
            exam=exam, title="সৃজনশীল", question_type=ExamSection.Type.CQ, marks=70, marks_per_question=10
        )

        self.assertEqual(self.add(section, self.cq_block()).status_code, 200)

    def test_a_group_whose_parts_disagree_is_refused_by_both(self):
        """One MCQ part in a creative stimulus makes it neither type."""
        mixed = self.mixed_block()
        cq_exam = self.exam(title="CQ paper")
        cq_section = self.section(exam=cq_exam, title="সৃজনশীল", question_type=ExamSection.Type.CQ, marks=70)

        self.assertEqual(self.add(self.section(), mixed).status_code, 422)
        self.assertEqual(self.add(cq_section, mixed).status_code, 422)

    def test_a_block_with_no_questions_is_refused(self):
        response = self.add(self.section(), self.empty_block())

        self.assertEqual(response.status_code, 422)
        self.assertIn("no questions", str(response.json()["errors"]))

    def test_a_retired_block_cannot_go_on_a_paper(self):
        block = self.mcq_block()
        QuestionBlock.objects.filter(pk=block.pk).update(is_active=False)

        self.assertEqual(self.add(self.section(), block).status_code, 422)

    def test_a_question_retired_after_joining_the_paper_does_not_lock_the_section(self):
        section, kept = self.section(), self.mcq_block()
        self.assertEqual(self.add(section, kept).status_code, 200)
        QuestionBlock.objects.filter(pk=kept.pk).update(is_active=False)

        added = self.mcq_block()
        self.assertEqual(self.add(section, added).status_code, 200)

        order = list(section.section_questions.order_by("order", "id").values_list("block_id", flat=True))
        self.assertEqual(order, [kept.pk, added.pk])

    def test_a_retired_question_can_be_taken_off_the_paper(self):
        section, retired, other = self.section(), self.mcq_block(), self.mcq_block()
        self.add(section, retired)
        self.add(section, other)
        QuestionBlock.objects.filter(pk=retired.pk).update(is_active=False)

        response = self.client.put(
            section_questions(section.pk), {"block_ids": [other.pk]}, content_type="application/json", **self.auth
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(list(section.section_questions.values_list("block_id", flat=True)), [other.pk])

    def test_a_block_from_another_subject_is_refused(self):
        self.assertEqual(self.add(self.section(), self.mcq_block(self.physics)).status_code, 422)

    def test_a_block_cannot_sit_in_two_sections_of_one_exam(self):
        exam = self.exam()
        first = self.section(exam=exam, title="MCQ", marks=30)
        second = self.section(exam=exam, title="More MCQ", marks=30)
        block = self.mcq_block()
        self.add(first, block)

        response = self.add(second, block)

        self.assertEqual(response.status_code, 422)
        self.assertIn("already in section", str(response.json()["errors"]))

    def test_the_same_block_may_appear_on_two_different_exams(self):
        """The bank is shared -- reusing a question is the point of having one."""
        block = self.mcq_block()
        self.add(self.section(), block)

        other = self.section(exam=self.exam(title="Another paper"))
        self.assertEqual(self.add(other, block).status_code, 200)

    def test_a_section_holding_mcq_blocks_refuses_to_become_creative(self):
        exam = self.exam()
        section = self.section(exam=exam)
        self.add(section, self.mcq_block())

        response = self.client.patch(
            detail("exam_section", section.pk),
            {"question_type": "cq"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("question_type", response.json()["errors"])

    def test_a_section_holding_blocks_refuses_to_change_subject(self):
        section = self.section()
        self.add(section, self.mcq_block())

        response = self.client.patch(
            detail("exam_section", section.pk),
            {"subject_id": self.physics.pk},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("subject_id", response.json()["errors"])


class BulkPickerTests(ExamTestCase):
    def setUp(self):
        super().setUp()
        self.section_row = self.section(marks=5)
        self.blocks = [self.mcq_block() for _ in range(5)]

    def put(self, block_ids, auth=None):
        return self.client.put(
            section_questions(self.section_row.pk),
            {"block_ids": block_ids},
            content_type="application/json",
            **(auth or self.auth),
        )

    def test_a_whole_section_is_picked_in_one_call(self):
        response = self.put([block.pk for block in self.blocks])

        self.assertEqual(response.status_code, 200)
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 5)
        self.assertEqual(self.section_row.computed_marks, Decimal("5.00"))

    def test_each_pick_takes_the_section_rate(self):
        self.section_row.marks_per_question = Decimal("2.00")
        self.section_row.save(update_fields=["marks_per_question"])

        self.put([block.pk for block in self.blocks])

        self.assertEqual(
            list(ExamSectionQuestion.objects.values_list("marks", flat=True)),
            [Decimal("2.00")] * 5,
        )

    def test_replace_leaves_every_pick_on_its_own_position(self):
        """Kept and added picks are numbered 0..n in the order sent."""
        first, second, third = self.blocks[:3]
        self.put([first.pk, second.pk])

        self.put([first.pk, third.pk, second.pk])

        picks = ExamSectionQuestion.objects.filter(section=self.section_row)
        orders = sorted(picks.values_list("order", flat=True))
        self.assertEqual(orders, [0, 1, 2], "two questions sharing a position")
        self.assertEqual(
            list(picks.order_by("order", "id").values_list("block_id", flat=True)),
            [first.pk, third.pk, second.pk],
        )

    def test_replace_drops_what_was_there(self):
        self.put([block.pk for block in self.blocks])

        self.put([self.blocks[0].pk])

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

    def test_one_bad_block_rolls_the_whole_call_back(self):
        good = [block.pk for block in self.blocks]

        response = self.put([*good, self.cq_block().pk])

        self.assertEqual(response.status_code, 422)
        self.assertEqual(ExamSectionQuestion.objects.count(), 0)

    def test_the_counters_are_right_even_though_bulk_create_skips_signals(self):
        self.put([block.pk for block in self.blocks])

        self.section_row.refresh_from_db()
        self.assertEqual(
            (self.section_row.question_count, self.section_row.computed_marks),
            (5, Decimal("5.00")),
        )

    def test_re_saving_the_same_picks_keeps_their_prices(self):
        self.put([block.pk for block in self.blocks])
        repriced = ExamSectionQuestion.objects.order_by("order").first()
        repriced.marks = Decimal("2.00")
        repriced.save(update_fields=["marks"])

        self.put([block.pk for block in self.blocks])

        repriced.refresh_from_db()
        self.assertEqual(repriced.marks, Decimal("2.00"))

    def test_re_saving_keeps_the_rows_themselves(self):
        self.put([block.pk for block in self.blocks])
        before = list(ExamSectionQuestion.objects.order_by("order").values_list("pk", flat=True))

        self.put([block.pk for block in self.blocks])

        after = list(ExamSectionQuestion.objects.order_by("order").values_list("pk", flat=True))
        self.assertEqual(before, after)

    def test_the_picked_order_becomes_the_paper_order(self):
        ids = [block.pk for block in self.blocks]
        self.put(ids)

        self.put(list(reversed(ids)))

        ordered = list(ExamSectionQuestion.objects.order_by("order").values_list("block_id", flat=True))
        self.assertEqual(ordered, list(reversed(ids)))

    def test_dropping_one_keeps_the_prices_of_the_others(self):
        self.put([block.pk for block in self.blocks])
        kept = ExamSectionQuestion.objects.order_by("order").last()
        kept.marks = Decimal("3.00")
        kept.save(update_fields=["marks"])

        self.put([block.pk for block in self.blocks[1:]])

        kept.refresh_from_db()
        self.assertEqual(kept.marks, Decimal("3.00"))
        self.assertEqual(ExamSectionQuestion.objects.count(), 4)


class SectionTotalsTests(ExamTestCase):
    """Counters hold however a pick was written, not just through the API."""

    def setUp(self):
        super().setUp()
        self.section_row = self.section()

    def pick(self, section=None, block=None, marks=1):
        return ExamSectionQuestion.objects.create(
            section=section or self.section_row, block=block or self.mcq_block(), marks=marks
        )

    def test_they_follow_a_pick_written_through_the_orm(self):
        """The Django admin and the shell write here, not through a serializer."""
        pick = self.pick()

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

        pick.delete()

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 0)

    def test_they_drop_when_the_picker_saves_an_empty_section(self):
        self.pick()
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

        self.client.put(
            section_questions(self.section_row.pk), {"block_ids": []}, content_type="application/json", **self.auth
        )

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 0)

    def test_a_pick_that_moves_decrements_the_section_it_left(self):
        exam = self.exam()
        origin = self.section(exam=exam, title="First")
        destination = self.section(exam=exam, title="Second")
        pick = self.pick(section=origin)

        moved = ExamSectionQuestion.objects.get(pk=pick.pk)
        moved.section = destination
        moved.save()

        origin.refresh_from_db()
        destination.refresh_from_db()
        self.assertEqual((origin.question_count, destination.question_count), (0, 1))

    def test_deleting_a_section_does_not_trip_over_its_own_picks(self):
        self.pick()

        self.section_row.delete()

        self.assertFalse(ExamSection.objects.filter(pk=self.section_row.pk).exists())

    def test_deleting_an_exam_cascades_without_raising(self):
        exam = self.exam(title="Doomed")
        section = self.section(exam=exam)
        self.pick(section=section)

        exam.delete()

        self.assertEqual(ExamSectionQuestion.objects.count(), 0)

    def test_they_are_recomputed_rather_than_incremented(self):
        self.pick()
        self.section_row.question_count = 99
        self.section_row.save(update_fields=["question_count"])

        section_service.sync_section_totals(self.section_row)

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

    def test_the_exam_totals_do_not_fan_out_across_sections(self):
        """A second to-many annotation would multiply the aggregates."""
        exam = self.exam()
        for title in ("First", "Second"):
            section = self.section(exam=exam, title=title)
            for _ in range(3):
                self.pick(section=section)

        body = self.client.get(detail("exam", exam.pk), **self.auth).json()

        self.assertEqual(body["section_count"], 2)
        self.assertEqual(body["selected_question_count"], 6)
        self.assertEqual(Decimal(body["computed_marks"]), Decimal("6.00"))


class BlockInUseTests(ExamTestCase):
    def test_a_block_on_a_paper_cannot_be_deleted(self):
        block = self.mcq_block()
        ExamSectionQuestion.objects.create(section=self.section(), block=block)

        response = self.client.delete(block_detail(block.pk), **self.auth)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(QuestionBlock.objects.filter(pk=block.pk).exists())

    def test_it_can_be_deleted_once_it_is_off_the_paper(self):
        block = self.mcq_block()
        pick = ExamSectionQuestion.objects.create(section=self.section(), block=block)
        pick.delete()

        self.assertEqual(self.client.delete(block_detail(block.pk), **self.auth).status_code, 204)


class PassageOnAPaperTests(ExamTestCase):
    """A passage (উদ্দীপক) with several MCQs under it."""

    def setUp(self):
        super().setUp()
        self.mcq_section = self.section(marks=25, marks_per_question=1)

    def place(self, section, block):
        """Places a block priced the way the picker prices it."""
        block.refresh_from_db()
        count = selectors.block_question_count(block, section.question_type)
        return ExamSectionQuestion.objects.create(
            section=section, block=block, marks=count * section.marks_per_question
        )

    def test_a_passage_of_mcqs_is_admissible_to_an_mcq_section(self):
        passage = self.mcq_passage(parts=3)

        validators.validate_section_blocks(section=self.mcq_section, blocks=[passage])

    def test_its_parts_keep_their_order(self):
        passage = self.mcq_passage(parts=3)

        orders = list(passage.question_set.questions.values_list("order_in_set", flat=True))
        self.assertEqual(orders, [0, 1, 2])

    def test_it_counts_and_costs_once_per_question(self):
        passage = self.mcq_passage(parts=3)
        self.place(self.mcq_section, passage)

        self.mcq_section.refresh_from_db()
        self.assertEqual(self.mcq_section.question_count, 3)
        self.assertEqual(self.mcq_section.computed_marks, Decimal("3.00"))

    def test_a_creative_block_still_counts_once_whatever_its_parts(self):
        """Four ক/খ/গ/ঘ parts are one সৃজনশীল question worth one rate."""
        cq_section = self.section(exam=self.mcq_section.exam, title="সৃজনশীল", marks=10, marks_per_question=10)
        cq_section.question_type = ExamSection.Type.CQ
        cq_section.save(update_fields=["question_type"])
        self.place(cq_section, self.cq_block())

        cq_section.refresh_from_db()
        self.assertEqual(cq_section.question_count, 1)
        self.assertEqual(cq_section.computed_marks, Decimal("10.00"))

    def test_a_section_mixing_singles_and_passages_adds_up(self):
        for _ in range(4):
            self.place(self.mcq_section, self.mcq_block())
        for _ in range(3):
            self.place(self.mcq_section, self.mcq_passage(parts=3))

        self.mcq_section.refresh_from_db()
        # 4 standalone + 3 passages x 3 = 13 questions, not 7 picks.
        self.assertEqual(self.mcq_section.question_count, 13)
        self.assertEqual(self.mcq_section.computed_marks, Decimal("13.00"))

    def test_the_picker_prices_a_passage_by_its_questions(self):
        passage = self.mcq_passage(parts=3)

        response = self.client.put(
            section_questions(self.mcq_section.pk),
            {"block_ids": [passage.pk]},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        pick = ExamSectionQuestion.objects.get(section=self.mcq_section, block=passage)
        self.assertEqual(pick.marks, Decimal("3.00"))


class SectionRateChangeTests(ExamTestCase):
    """Changing marks per question re-prices the picks, so the paper's totals stay true."""

    def setUp(self):
        super().setUp()
        self.section_row = self.section(marks=5, marks_per_question=1)
        self.singles = [
            ExamSectionQuestion.objects.create(section=self.section_row, block=self.mcq_block(), marks=1)
            for _ in range(2)
        ]
        self.passage = ExamSectionQuestion.objects.create(
            section=self.section_row, block=self.mcq_passage(parts=3), marks=3
        )

    def patch_rate(self, rate, **extra):
        return self.client.patch(
            detail("exam_section", self.section_row.pk),
            {"marks_per_question": rate, **extra},
            content_type="application/json",
            **self.auth,
        )

    def test_the_picks_follow_the_new_rate(self):
        response = self.patch_rate("2.00", marks="10.00")

        self.assertEqual(response.status_code, 200, response.content)
        marks = [pick.marks for pick in ExamSectionQuestion.objects.filter(section=self.section_row).order_by("pk")]
        self.assertEqual(marks, [Decimal("2.00"), Decimal("2.00"), Decimal("6.00")])
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.computed_marks, Decimal("10.00"))

    def test_a_stale_total_no_longer_passes_publishing(self):
        """Raising the rate without the section's marks must not publish a paper graded out of more."""
        self.patch_rate("2.00")

        self.section_row.refresh_from_db()
        problems = [message for _, message in validators.section_problems(self.section_row)]
        self.assertIn("its questions add up to 10.00", " ".join(problems))

    def test_a_pick_priced_by_hand_keeps_its_price(self):
        ExamSectionQuestion.objects.filter(pk=self.singles[0].pk).update(marks=Decimal("1.50"))

        self.patch_rate("2.00", marks="10.00")

        self.singles[0].refresh_from_db()
        self.assertEqual(self.singles[0].marks, Decimal("1.50"))

    def test_a_section_loaded_with_only_some_fields_still_reprices(self):
        section = ExamSection.objects.only("pk", "exam_id", "question_type", "title").get(pk=self.section_row.pk)
        section.marks_per_question = Decimal("2.00")
        section.save()
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.computed_marks, Decimal("10.00"))

    def test_saving_other_fields_reprices_nothing(self):
        ExamSectionQuestion.objects.filter(pk=self.singles[0].pk).update(marks=Decimal("1.50"))
        self.client.patch(
            detail("exam_section", self.section_row.pk),
            {"title": "Part A"},
            content_type="application/json",
            **self.auth,
        )
        self.singles[0].refresh_from_db()
        self.assertEqual(self.singles[0].marks, Decimal("1.50"))


class AutoMarkedPickPriceTests(ExamTestCase):
    """Grading marks each MCQ at the section's rate, so a pick there cannot be priced by hand."""

    def setUp(self):
        super().setUp()
        self.mcq_section = self.section(marks=5, marks_per_question=1)

    def test_a_hand_price_on_an_mcq_section_is_refused(self):
        pick = ExamSectionQuestion(section=self.mcq_section, block=self.mcq_block(), marks=Decimal("2.00"))
        with self.assertRaises(ValidationError) as refused:
            pick.full_clean()
        self.assertIn("marks", refused.exception.message_dict)

    def test_the_rate_price_is_accepted(self):
        ExamSectionQuestion(
            section=self.mcq_section, block=self.mcq_passage(parts=3), marks=Decimal("3.00")
        ).full_clean()

    def test_a_creative_section_may_still_price_by_hand(self):
        cq = self.section(exam=self.mcq_section.exam, title="সৃজনশীল", marks=10, marks_per_question=10)
        cq.question_type = ExamSection.Type.CQ
        cq.save(update_fields=["question_type"])
        ExamSectionQuestion(section=cq, block=self.cq_block(), marks=Decimal("12.00")).full_clean()

    def test_a_passage_that_gains_a_question_is_repriced(self):
        passage = self.mcq_passage(parts=3)
        pick = ExamSectionQuestion.objects.create(section=self.mcq_section, block=passage, marks=3)
        Question.objects.create(
            question_set=passage.question_set, question_type=Question.Type.MCQ, order_in_set=3, prompt_content="4th"
        )
        sync_question_count(passage)

        pick.refresh_from_db()
        self.mcq_section.refresh_from_db()
        self.assertEqual(pick.marks, Decimal("4.00"))
        self.assertEqual(self.mcq_section.computed_marks, Decimal("4.00"))


class LivePaperRepriceTests(ExamTestCase):
    def test_a_published_paper_keeps_its_prices_when_a_block_changes(self):
        section = self.section(marks=3, marks_per_question=1)
        passage = self.mcq_passage(parts=3)
        pick = ExamSectionQuestion.objects.create(section=section, block=passage, marks=3)
        sync_section_totals(section)
        Exam.objects.filter(pk=section.exam_id).update(status=Exam.Status.PUBLISHED)

        Question.objects.create(
            question_set=passage.question_set, question_type=Question.Type.MCQ, order_in_set=3, prompt_content="4th"
        )
        sync_question_count(passage)

        pick.refresh_from_db()
        section.refresh_from_db()
        self.assertEqual((pick.marks, section.computed_marks), (Decimal("3.00"), Decimal("3.00")))

    def test_a_large_passage_fits_its_price(self):
        section = self.section(marks=200, marks_per_question=2)
        pick = ExamSectionQuestion(section=section, block=self.mcq_passage(parts=60), marks=Decimal("120.00"))
        pick.full_clean()
        pick.save()


class SectionBlocksRelationTests(ExamTestCase):
    """`ExamSection.blocks` reads the same rows as `section_questions`."""

    def test_it_sees_the_picked_blocks(self):
        section = self.section()
        first, second = self.mcq_block(), self.mcq_block()
        ExamSectionQuestion.objects.create(section=section, block=first, order=0)
        ExamSectionQuestion.objects.create(section=section, block=second, order=1)

        self.assertEqual(section.blocks.count(), 2)
        self.assertCountEqual(section.blocks.values_list("pk", flat=True), [first.pk, second.pk])

    def test_it_reads_back_from_the_block(self):
        section = self.section()
        block = self.mcq_block()
        ExamSectionQuestion.objects.create(section=section, block=block)

        self.assertEqual(list(block.exam_sections.all()), [section])

    def test_the_paper_order_lives_on_the_pick_not_the_m2m(self):
        section = self.section()
        first, second = self.mcq_block(), self.mcq_block()
        # Picked in the reverse of the bank's order.
        ExamSectionQuestion.objects.create(section=section, block=second, order=0)
        ExamSectionQuestion.objects.create(section=section, block=first, order=1)

        on_the_paper = list(section.section_questions.order_by("order", "id").values_list("block_id", flat=True))
        self.assertEqual(on_the_paper, [second.pk, first.pk])
        self.assertEqual(list(section.blocks.values_list("pk", flat=True)), [first.pk, second.pk])

    def test_adding_through_the_m2m_skips_order_and_counters(self):
        """`.add()` through the M2M shares `order = 0` and skips the counter signals."""
        section = self.section()
        first, second = self.mcq_block(), self.mcq_block()

        section.blocks.add(first, second)

        self.assertEqual([pick.order for pick in section.section_questions.all()], [0, 0])
        section.refresh_from_db()
        self.assertEqual(section.question_count, 0)
        self.assertEqual(section.computed_marks, 0)

        section_service.sync_section_totals(section)
        section.refresh_from_db()
        self.assertEqual(section.question_count, 2)
