"""Publishing a paper, what a published paper freezes, and its header."""

from decimal import Decimal

from django.core.exceptions import ValidationError

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.tests.base import (
    EXAMS_URL,
    ExamTestCase,
    block_detail,
    detail,
    section_questions,
)
from apps.question.models import Question
from apps.question.tests.base import save_question


class PublishTests(ExamTestCase):
    def publish(self, exam):
        return self.client.patch(
            detail("exam", exam.pk),
            {"status": "published"},
            content_type="application/json",
            **self.auth,
        )

    def fill(self, section, count):
        for _ in range(count):
            ExamSectionQuestion.objects.create(
                section=section, block=self.mcq_block(), marks=section.marks_per_question
            )
        section.refresh_from_db()
        return section

    def test_an_exam_with_no_sections_cannot_be_published(self):
        response = self.publish(self.exam())

        self.assertEqual(response.status_code, 422)
        self.assertIn("status", response.json()["errors"])

    def test_an_empty_section_blocks_publishing(self):
        exam = self.exam(total_marks=30)
        self.section(exam=exam, marks=30)

        self.assertEqual(self.publish(exam).status_code, 422)

    def test_a_marks_mismatch_blocks_publishing(self):
        exam = self.exam(total_marks=30)
        self.fill(self.section(exam=exam, marks=30), 28)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 422)
        self.assertIn("add up to", str(response.json()["errors"]))

    def test_pass_marks_above_the_paper_block_publishing(self):
        """The total is what the sections add up to, so the pass mark is checked against it here."""
        exam = self.exam(pass_marks=40)
        self.fill(self.section(exam=exam, marks=30), 30)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 422)
        self.assertIn("pass_marks", response.json()["errors"])

    def test_a_complete_exam_publishes(self):
        exam = self.exam(total_marks=30)
        self.fill(self.section(exam=exam, marks=30), 30)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "published")

    def test_answer_any_seven_of_eleven_publishes_at_seventy(self):
        """Marks count only the required answers: 7 × 10, not 11 × 10."""
        exam = self.exam(total_marks=70)
        section = self.section(
            exam=exam,
            title="সৃজনশীল",
            question_type=ExamSection.Type.CQ,
            marks=70,
            marks_per_question=10,
            required_question_count=7,
        )
        for _ in range(11):
            ExamSectionQuestion.objects.create(section=section, block=self.cq_block(), marks=10)

        self.assertEqual(self.publish(exam).status_code, 200, self.publish(exam).content)

    def test_a_section_cannot_require_more_answers_than_it_offers(self):
        exam = self.exam(total_marks=30)
        section = self.section(exam=exam, marks=30, required_question_count=30)
        self.fill(section, 5)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 422)
        self.assertIn("only offers", str(response.json()["errors"]))

    def test_a_single_type_paper_publishes(self):
        exam = self.exam(total_marks=30)
        self.fill(self.section(exam=exam, marks=30), 30)

        self.assertEqual(self.publish(exam).status_code, 200)

    def setUp(self):
        super().setUp()
        self.exam_row = self.exam(total_marks=3)
        self.section_row = self.section(exam=self.exam_row, marks=3)
        self.blocks = [self.mcq_block() for _ in range(3)]
        for block in self.blocks:
            ExamSectionQuestion.objects.create(section=self.section_row, block=block, marks=1)
        response = self.client.patch(
            detail("exam", self.exam_row.pk),
            {"status": "published"},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

    def patch(self, resource, pk, payload):
        return self.client.patch(detail(resource, pk), payload, content_type="application/json", **self.auth)

    def test_its_questions_cannot_be_replaced(self):
        response = self.client.put(
            section_questions(self.section_row.pk),
            {"block_ids": [self.blocks[0].pk]},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 3)

    def test_a_question_cannot_be_added(self):
        kept = list(self.section_row.section_questions.values_list("block_id", flat=True))
        response = self.client.put(
            section_questions(self.section_row.pk),
            {"block_ids": [*kept, self.mcq_block().pk]},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)

    def test_a_question_cannot_be_dropped(self):
        pick = ExamSectionQuestion.objects.first()
        kept = self.section_row.section_questions.exclude(pk=pick.pk).values_list("block_id", flat=True)

        response = self.client.put(
            section_questions(self.section_row.pk),
            {"block_ids": list(kept)},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertTrue(ExamSectionQuestion.objects.filter(pk=pick.pk).exists())

    def test_a_section_cannot_be_reworked_or_removed(self):
        # A value the section rules alone would accept.
        response = self.patch("exam_section", self.section_row.pk, {"marks": "2"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("status", response.json()["errors"])
        self.assertEqual(self.client.delete(detail("exam_section", self.section_row.pk), **self.auth).status_code, 422)

    def test_its_total_marks_cannot_be_typed(self):
        """The total is derived from the sections; a sent value is ignored."""
        before = self.exam_row.total_marks
        response = self.patch("exam", self.exam_row.pk, {"total_marks": "9"})

        self.assertEqual(response.status_code, 200, response.content)
        self.exam_row.refresh_from_db()
        self.assertEqual(self.exam_row.total_marks, before)

    def test_but_it_can_still_be_renamed_and_rescheduled(self):
        response = self.patch(
            "exam",
            self.exam_row.pk,
            {"title": "Renamed", "start_time": "2026-11-01T10:00:00Z"},
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["title"], "Renamed")

    def test_moving_back_to_draft_unfreezes_it(self):
        self.assertEqual(self.patch("exam", self.exam_row.pk, {"status": "draft"}).status_code, 200)

        self.assertEqual(self.patch("exam_section", self.section_row.pk, {"marks": "2"}).status_code, 200)

    def test_a_paper_broken_out_of_band_can_still_be_renamed(self):
        """The publish rules run on the transition, not on every later edit."""
        ExamSectionQuestion.objects.filter(section=self.section_row).first().delete()

        response = self.patch("exam", self.exam_row.pk, {"title": "Renamed anyway"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["title"], "Renamed anyway")

    def test_the_django_admin_cannot_break_a_published_paper_either(self):
        # Re-fetched so the cached `exam` is not the pre-publish draft.
        section = ExamSection.objects.select_related("exam").get(pk=self.section_row.pk)
        section.marks = Decimal("2.00")

        with self.assertRaises(ValidationError):
            section.clean()

    def test_archiving_is_how_an_exam_is_retired(self):
        response = self.patch("exam", self.exam_row.pk, {"status": "archived"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "archived")


class PaperIntegrityTests(ExamTestCase):
    """A paper's contents cannot change around it, from the exam side or the question bank."""

    def placed(self, block, *, published=False, **section_overrides):
        section = self.section(**{"marks": 1, **section_overrides})
        pick = ExamSectionQuestion.objects.create(section=section, block=block, marks=1)
        if published:
            Exam.objects.filter(pk=section.exam_id).update(status=Exam.Status.PUBLISHED)
        return section, pick

    def test_a_section_cannot_move_to_another_exam(self):
        section, _ = self.placed(self.mcq_block(), published=True)
        response = self.client.patch(
            detail("exam_section", section.pk),
            {"exam_id": self.exam(title="Draft").pk},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("exam_id", response.json()["errors"])

    def test_a_placed_block_keeps_its_subject(self):
        block = self.mcq_block()
        self.placed(block)
        response = self.client.patch(
            block_detail(block.pk), {"subject_id": self.physics.pk}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("subject_id", response.json()["errors"])

    def test_a_placed_question_keeps_its_type(self):
        block = self.mcq_block()
        self.placed(block)
        response = save_question(
            self.client, self.auth, {"question_type": "cq", "options": []}, question=block.standalone_question
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("question_type", response.json()["errors"])

    def test_a_part_of_another_type_cannot_join_a_placed_passage(self):
        passage = self.mcq_passage(parts=2)
        self.placed(passage)
        response = save_question(
            self.client,
            self.auth,
            {"question_set_id": passage.question_set.pk, "question_type": "cq", "prompt_content": "?"},
        )
        self.assertEqual(response.status_code, 422)

    def test_a_published_paper_keeps_its_parts(self):
        passage = self.mcq_passage(parts=2)
        self.placed(passage, published=True)
        added = save_question(
            self.client,
            self.auth,
            {
                "question_set_id": passage.question_set.pk,
                "question_type": "mcq",
                "prompt_content": "?",
                "options": [{"content": "a", "is_correct": True, "position": 0}],
            },
        )
        removed = save_question(
            self.client,
            self.auth,
            {"question_set_id": passage.question_set.pk},
            removed=[passage.question_set.questions.first().pk],
        )
        self.assertEqual((added.status_code, removed.status_code), (422, 422))
        self.assertEqual(passage.question_set.questions.count(), 2)

    def test_wording_stays_editable_on_a_published_paper(self):
        """A typo on a live paper has to be fixable."""
        block = self.mcq_block()
        block.standalone_question.options.create(content="4", is_correct=True, position=0)
        self.placed(block, published=True)
        response = save_question(
            self.client, self.auth, {"prompt_content": "2 + 2 = ? (fixed)"}, question=block.standalone_question
        )
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_new_part_is_counted_on_a_draft_paper(self):
        passage = self.mcq_passage(parts=2)
        section, _ = self.placed(passage)
        section.refresh_from_db()
        self.assertEqual(section.question_count, 2)

        Question.objects.create(question_set=passage.question_set, question_type=Question.Type.MCQ, prompt_content="?")
        section.refresh_from_db()
        self.assertEqual(section.question_count, 3)


class PaperHeaderTests(ExamTestCase):
    def build_paper(self):
        """The user's sketch: 30 MCQ answer 25, 11 CQ answer 7."""
        exam = self.exam(total_marks=95, duration_minutes=60)
        mcq = self.section(exam=exam, title="MCQ", marks=25, marks_per_question=1, required_question_count=25)
        for _ in range(30):
            ExamSectionQuestion.objects.create(section=mcq, block=self.mcq_block(), marks=1)
        cq = self.section(
            exam=exam,
            title="সৃজনশীল",
            question_type=ExamSection.Type.CQ,
            marks=70,
            marks_per_question=10,
            required_question_count=7,
        )
        for _ in range(11):
            ExamSectionQuestion.objects.create(section=cq, block=self.cq_block(), marks=10)
        return exam

    def header(self, exam):
        return self.client.get(detail("exam", exam.pk), **self.auth).json()["paper"]

    def test_it_states_each_part_the_way_the_paper_prints_it(self):
        header = self.header(self.build_paper())

        mcq, cq = header["parts"]
        self.assertEqual(
            (mcq["questions_given"], mcq["answers_required"], mcq["marks_per_question"]),
            (30, 25, "1.00"),
        )
        self.assertEqual(mcq["target_marks"], "25.00")
        self.assertEqual(
            (cq["questions_given"], cq["answers_required"], cq["marks_per_question"]),
            (11, 7, "10.00"),
        )
        # 7 x 10, not the 110 marks the eleven questions offer.
        self.assertEqual(cq["target_marks"], "70.00")

    def test_each_part_prints_its_own_rubric(self):
        """The paper and each part have their own instructions."""
        exam = self.build_paper()
        exam.instructions = "ডান পাশের সংখ্যা প্রশ্নের পূর্ণমান জ্ঞাপক"
        exam.save(update_fields=["instructions"])
        mcq_section, cq_section = ExamSection.objects.filter(exam=exam).order_by("order", "id")
        mcq_section.instructions = "সকল প্রশ্নের উত্তর দাও"
        mcq_section.save(update_fields=["instructions"])
        cq_section.instructions = "যেকোনো ৬টি প্রশ্নের উত্তর দাও"
        cq_section.save(update_fields=["instructions"])

        header = self.header(exam)

        self.assertEqual(header["instructions"], "ডান পাশের সংখ্যা প্রশ্নের পূর্ণমান জ্ঞাপক")
        self.assertEqual(header["parts"][0]["instructions"], "সকল প্রশ্নের উত্তর দাও")
        self.assertEqual(header["parts"][1]["instructions"], "যেকোনো ৬টি প্রশ্নের উত্তর দাও")

    def test_the_creative_part_shows_no_negative_marking(self):
        """A creative part shows zero negative marking whatever was entered."""
        exam = self.build_paper()
        ExamSection.objects.filter(exam=exam).update(negative_marks=Decimal("0.25"))

        mcq, cq = self.header(exam)["parts"]

        self.assertEqual(mcq["negative_marks"], "0.25")
        self.assertEqual(cq["negative_marks"], "0.00")

    def test_answers_required_falls_back_to_every_question(self):
        exam = self.exam(total_marks=3)
        section = self.section(exam=exam, marks=3)
        for _ in range(3):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)

        part = self.header(exam)["parts"][0]

        self.assertEqual((part["questions_given"], part["answers_required"]), (3, 3))

    def test_it_reports_the_declared_number_and_the_computed_one(self):
        exam = self.exam(total_marks=30)
        section = self.section(exam=exam, marks=30)
        for _ in range(28):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)

        part = self.header(exam)["parts"][0]

        self.assertEqual(part["marks"], "30.00")
        self.assertEqual(part["computed_marks"], "28.00")
        self.assertTrue(part["problems"])

    def test_the_multiplication_is_hidden_when_it_would_not_add_up(self):
        """A repriced pick makes "rate × count" untrue."""
        exam = self.exam(total_marks=31)
        section = self.section(exam=exam, marks=31)
        for _ in range(29):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)
        ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=2)

        part = self.header(exam)["parts"][0]

        self.assertFalse(part["shows_multiplication"])
        self.assertEqual(part["computed_marks"], "31.00")

    def test_its_problems_are_the_publish_errors_verbatim(self):
        exam = self.exam(total_marks=30)
        section = self.section(exam=exam, marks=30)
        for _ in range(28):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)

        refusal = self.client.patch(
            detail("exam", exam.pk),
            {"status": "published"},
            content_type="application/json",
            **self.auth,
        ).json()["errors"]["status"][0]

        self.assertIn(refusal, self.header(exam)["parts"][0]["problems"])

    def test_a_publishable_paper_has_nothing_to_report(self):
        exam = self.exam(total_marks=3)
        section = self.section(exam=exam, marks=3)
        for _ in range(3):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)

        header = self.header(exam)

        self.assertEqual(header["problems"], [])
        self.assertEqual(header["parts"][0]["problems"], [])
        self.assertTrue(header["matches_total"])

    def test_an_empty_paper_does_not_raise(self):
        header = self.header(self.exam())

        self.assertEqual(header["parts"], [])
        self.assertFalse(header["matches_total"])
        self.assertTrue(header["problems"])

    def test_every_amount_is_a_string_like_the_rest_of_the_payload(self):
        exam = self.build_paper()
        body = self.client.get(detail("exam", exam.pk), **self.auth).json()

        self.assertIsInstance(body["total_marks"], str)
        self.assertIsInstance(body["paper"]["total_marks"], str)
        self.assertIsInstance(body["paper"]["parts"][0]["marks"], str)

    def test_the_list_carries_no_header(self):
        """The header would need every section of every row."""
        self.build_paper()

        self.assertNotIn("paper", self.client.get(EXAMS_URL, **self.auth).json()["data"][0])


class AdminSitePublishTests(ExamTestCase):
    """The Django admin enforces the API's publishing rules."""

    def form(self, exam, **changes):
        from django.contrib import admin

        model_admin = admin.site._registry[Exam]
        Form = model_admin.get_form(request=None, obj=exam, change=True, fields=["title", "status", "scope"])
        data = {"title": exam.title, "status": exam.status, "scope": exam.scope, **changes}
        return Form(data=data, instance=exam)

    def test_an_empty_paper_cannot_be_published_from_the_admin(self):
        form = self.form(self.exam(), status=Exam.Status.PUBLISHED)

        self.assertFalse(form.is_valid())
        self.assertIn("status", form.errors)

    def test_a_published_exam_keeps_its_scope_in_the_admin(self):
        exam = self.exam()
        Exam.objects.filter(pk=exam.pk).update(status=Exam.Status.PUBLISHED)
        exam.refresh_from_db()

        form = self.form(exam, scope=Exam.Scope.STANDALONE if exam.scope != Exam.Scope.STANDALONE else Exam.Scope.BATCH)

        self.assertFalse(form.is_valid())
