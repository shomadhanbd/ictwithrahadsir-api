"""Exam authoring: composition rules, ownership, counters and the picker."""

from decimal import Decimal
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject
from apps.exam import services
from apps.exam.api.private.permissions import IsExamAuthor
from apps.exam.api.private.views import exam_queryset
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.identity.models import User
from apps.question.models import Question, QuestionBlock, QuestionSet

EXAMS_URL = reverse("api:exam:admin_exam_list")
SECTIONS_URL = reverse("api:exam:admin_exam_section_list")
PICKS_URL = reverse("api:exam:admin_exam_section_question_list")
BLOCKS_URL = reverse("api:question:admin_question_block_list")


def detail(resource, pk):
    return reverse(f"api:exam:admin_{resource}_detail", args=[pk])


def section_questions(pk):
    return reverse("api:exam:admin_exam_section_question_bulk", args=[pk])


def block_detail(pk):
    return reverse("api:question:admin_question_block_detail", args=[pk])


class ExamTestCase(TestCase):
    def setUp(self):
        self.admin = self._user("01700001111", User.Role.ADMIN)
        self.teacher = self._user("01700002222", User.Role.TEACHER)
        self.other_teacher = self._user("01700003333", User.Role.TEACHER)

        self.auth = self._auth(self.admin)
        self.teacher_auth = self._auth(self.teacher)
        self.other_auth = self._auth(self.other_teacher)

        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc")
        self.ssc = ClassLevel.objects.create(name="এসএসসি", slug="ssc")
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc")
        self.physics = Subject.objects.create(
            name="Physics", class_level=self.hsc, group=self.science, slug="physics-hsc"
        )
        self.chapter = Chapter.objects.create(name="Number Systems", subject=self.ict, chapter_number=1)

    @staticmethod
    def _user(phone, role):
        return User.objects.create_user(phone=phone, name=f"User {phone}", password="Str0ngPass!23", role=role)

    @staticmethod
    def _auth(user):
        return {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=user).key}"}

    # -- fixtures ------------------------------------------------------------

    def exam(self, **overrides):
        return Exam.objects.create(
            **{"title": "HSC ICT মডেল টেস্ট", "created_by": self.admin, "total_marks": 100, **overrides}
        )

    def section(self, exam=None, **overrides):
        return ExamSection.objects.create(
            **{
                "exam": exam or self.exam(),
                "title": "MCQ",
                "question_type": ExamSection.Type.MCQ,
                "subject": self.ict,
                "marks": 30,
                "marks_per_question": 1,
                **overrides,
            }
        )

    def mcq_block(self, subject=None):
        """A standalone block whose single question is an MCQ."""
        block = QuestionBlock.objects.create(subject=subject or self.ict)
        Question.objects.create(block=block, question_type=Question.Type.MCQ, prompt_content="2 + 2 = ?")
        return block

    def cq_block(self, subject=None):
        """A group block: one stimulus, four creative-question parts."""
        block = QuestionBlock.objects.create(subject=subject or self.ict, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="উদ্দীপক")
        for order, label in enumerate(["ক", "খ", "গ", "ঘ"]):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.CQ,
                label=label,
                order_in_set=order,
                prompt_content=f"part {label}",
            )
        return block

    def mcq_passage(self, parts=3, subject=None):
        """A group block: one passage (উদ্দীপক), N MCQs under it.

        The case an MCQ paper carries all the time, and the one that makes a
        block stop being a single question.
        """
        block = QuestionBlock.objects.create(subject=subject or self.ict, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="একটি অনুচ্ছেদ")
        for order in range(parts):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.MCQ,
                order_in_set=order,
                prompt_content=f"passage question {order + 1}",
            )
        block.refresh_from_db()
        return block

    def mixed_block(self):
        """A group whose parts disagree -- admissible to neither section type."""
        block = self.cq_block()
        block.question_set.questions.filter(label="ক").update(question_type=Question.Type.MCQ)
        return block

    def empty_block(self):
        """Authored but not yet given a question -- routine in a live bank."""
        return QuestionBlock.objects.create(subject=self.ict)


class ExamAuthoringTests(ExamTestCase):
    def post(self, **overrides):
        payload = {"title": "HSC ICT মডেল টেস্ট", "total_marks": "100.00", **overrides}
        return self.client.post(EXAMS_URL, payload, content_type="application/json", **self.auth)

    def test_an_exam_is_created_with_sane_defaults(self):
        response = self.post()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "draft")
        self.assertEqual(body["scope"], "standalone")
        self.assertEqual(body["max_attempts"], 1)

    def test_a_bangla_title_is_slugged_by_transliteration(self):
        """Django's `slugify` strips Bengali vowel marks, so a blank slug goes
        through `apps.core.slugs` instead."""
        slug = self.post().json()["slug"]

        self.assertTrue(slug)
        self.assertNotIn(" ", slug)

    def test_the_author_comes_from_the_token(self):
        response = self.client.post(
            EXAMS_URL,
            {"title": "Teacher's paper", "total_marks": "50.00"},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Exam.objects.get(pk=response.json()["id"]).created_by, self.teacher)

    def test_the_author_cannot_be_spoofed_in_the_payload(self):
        response = self.client.post(
            EXAMS_URL,
            {"title": "Forged", "total_marks": "50.00", "created_by_id": self.admin.pk},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Exam.objects.get(pk=response.json()["id"]).created_by, self.teacher)

    def test_the_list_is_enveloped_and_the_detail_is_not(self):
        exam = self.exam()

        listed = self.client.get(EXAMS_URL, **self.auth).json()
        self.assertEqual(listed["meta"]["total"], 1)
        self.assertEqual([row["id"] for row in listed["data"]], [exam.pk])

        self.assertEqual(self.client.get(detail("exam", exam.pk), **self.auth).json()["id"], exam.pk)


class ExamConfigurationRuleTests(ExamTestCase):
    def post(self, **overrides):
        payload = {"title": "Rules", "total_marks": "100.00", **overrides}
        return self.client.post(EXAMS_URL, payload, content_type="application/json", **self.auth)

    def assert_refused(self, field, **overrides):
        response = self.post(**overrides)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn(field, response.json()["errors"])

    def test_pass_marks_cannot_exceed_the_total(self):
        self.assert_refused("pass_marks", pass_marks="120.00")

    def test_total_marks_must_be_positive(self):
        self.assert_refused("total_marks", total_marks="0.00")

    def test_an_exam_cannot_end_before_it_starts(self):
        self.assert_refused("end_time", start_time="2026-10-01T10:00:00Z", end_time="2026-10-01T09:00:00Z")

    def test_results_cannot_publish_before_the_exam_closes(self):
        self.assert_refused(
            "result_publish_time",
            start_time="2026-10-01T10:00:00Z",
            end_time="2026-10-01T12:00:00Z",
            result_publish_time="2026-10-01T11:00:00Z",
        )

    def test_an_exam_allows_at_least_one_attempt(self):
        self.assert_refused("max_attempts", max_attempts=0)

    def test_a_batch_exam_needs_a_batch(self):
        self.assert_refused("batch_id", scope="batch")

    def test_a_course_scope_no_longer_exists(self):
        """It was modelled and validated but never offered, and pointed at the
        app most likely to be rewritten."""
        response = self.post(scope="course")

        self.assertEqual(response.status_code, 422)
        self.assertIn("scope", response.json()["errors"])

    def test_a_standalone_exam_carries_no_scope_column(self):
        batch = Batch.objects.create(name="SSC-2027", class_level=self.ssc, slug="ssc-2027")

        self.assert_refused("scope", scope="standalone", batch_id=batch.pk)

    def test_the_database_refuses_pass_marks_above_the_total(self):
        """The serializer catches this first, so without a test on the ORM path
        the constraint itself would never be exercised."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exam.objects.create(title="Raw", total_marks=10, pass_marks=20)

    def test_the_database_refuses_a_zero_attempt_exam(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Exam.objects.create(title="Raw", max_attempts=0)


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
        """There is no "paper type" to contradict any more. The old enum had
        one member per *combination* of question types, so a third type would
        have needed a fourth member, then an eighth."""
        exam = self.exam()

        self.assertEqual(self.post(exam=exam, title="MCQ", marks="30.00").status_code, 201)
        self.assertEqual(self.post(exam=exam, title="সৃজনশীল", question_type="cq", marks="70.00").status_code, 201)

    def test_a_paper_reports_the_types_it_contains(self):
        exam = self.exam()
        self.post(exam=exam, title="MCQ", marks="30.00")
        self.post(exam=exam, title="সৃজনশীল", question_type="cq", marks="70.00")

        body = self.client.get(detail("exam", exam.pk), **self.auth).json()

        self.assertEqual(body["question_types"], ["mcq", "cq"])

    def test_the_sections_cannot_outgrow_the_exam(self):
        exam = self.exam(total_marks=100)
        self.section(exam=exam, title="MCQ", marks=80)

        response = self.post(exam=exam, title="Extra", marks="30.00")

        self.assertEqual(response.status_code, 422)
        self.assertIn("marks", response.json()["errors"])

    def test_the_sections_cannot_outrun_the_exam(self):
        exam = self.exam(duration_minutes=90)
        self.section(exam=exam, title="MCQ", marks=30, duration_minutes=60)

        response = self.post(exam=exam, title="Second", marks="30.00", duration_minutes=45)

        self.assertEqual(response.status_code, 422)
        self.assertIn("duration_minutes", response.json()["errors"])

    def test_a_subject_from_another_class_level_is_refused_on_a_batch_exam(self):
        """`Subject` is a (name, class_level, group) triple and a `Batch` names a
        class level, so an HSC subject on an SSC paper is catchable."""
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
        return self.client.post(
            PICKS_URL,
            {"section_id": section.pk, "block_id": block.pk},
            content_type="application/json",
            **(auth or self.auth),
        )

    def test_an_mcq_block_joins_an_mcq_section(self):
        self.assertEqual(self.add(self.section(), self.mcq_block()).status_code, 201)

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

        self.assertEqual(self.add(section, self.cq_block()).status_code, 201)

    def test_a_group_whose_parts_disagree_is_refused_by_both(self):
        """One MCQ part in an otherwise creative-question stimulus. It is not
        wholly either type, so neither section may take it."""
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
        self.assertEqual(self.add(other, block).status_code, 201)

    def test_a_section_holding_mcq_blocks_refuses_to_become_creative(self):
        """The mirror of the block rule. Guarding only one side is how the
        question app's `kind` check let a standalone block take a stimulus set."""
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

    def put(self, block_ids, mode="append", auth=None):
        return self.client.put(
            section_questions(self.section_row.pk),
            {"block_ids": block_ids, "mode": mode},
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
        """A replace that keeps some blocks and adds others must still number
        the paper 0, 1, 2, ... -- the order the blocks were sent in.

        The two halves are written separately: added rows are numbered as they
        are created, survivors are renumbered afterwards. Numbering the added
        rows by their index *among the added* rather than by their place in the
        paper makes the two halves collide.
        """
        first, second, third = self.blocks[:3]
        self.put([first.pk, second.pk])

        # `first` stays at position 0, `third` is inserted between them, and
        # `second` slides to 2. The added row is numbered from zero, so it
        # lands on the position `first` never moved off.
        self.put([first.pk, third.pk, second.pk], mode="replace")

        picks = ExamSectionQuestion.objects.filter(section=self.section_row)
        orders = sorted(picks.values_list("order", flat=True))
        self.assertEqual(orders, [0, 1, 2], "two questions sharing a position")
        self.assertEqual(
            list(picks.order_by("order", "id").values_list("block_id", flat=True)),
            [first.pk, third.pk, second.pk],
        )

    def test_replace_drops_what_was_there(self):
        self.put([block.pk for block in self.blocks])

        self.put([self.blocks[0].pk], mode="replace")

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

    def test_one_bad_block_rolls_the_whole_call_back(self):
        """A failure at item five must not leave four picked -- a half-built
        section is worse than a refused one."""
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

    def test_the_picker_reads_back_the_whole_block_tree(self):
        self.put([self.blocks[0].pk])

        body = self.client.get(section_questions(self.section_row.pk), **self.auth).json()

        self.assertEqual(list(body), ["data"])
        self.assertEqual(body["data"][0]["block"]["id"], self.blocks[0].pk)

    def test_re_saving_the_same_picks_keeps_their_prices(self):
        """Re-opening the picker and saving without changing anything used to
        reset every repriced question to the section rate."""
        self.put([block.pk for block in self.blocks])
        repriced = ExamSectionQuestion.objects.order_by("order").first()
        repriced.marks = Decimal("2.00")
        repriced.save(update_fields=["marks"])

        self.put([block.pk for block in self.blocks])

        repriced.refresh_from_db()
        self.assertEqual(repriced.marks, Decimal("2.00"))

    def test_re_saving_keeps_the_rows_themselves(self):
        """Nothing reads a pick's id yet; a submission's answer will, and the
        question app already learned this one about option ids."""
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

    def test_appending_a_block_already_on_the_section_is_a_no_op(self):
        """`(section, block)` is unique, so a repeated append used to be an
        IntegrityError -- a 500 for pressing the same button twice."""
        first = self.blocks[0].pk
        self.put([first])

        response = self.client.post(
            section_questions(self.section_row.pk),
            {"block_ids": [first, self.blocks[1].pk], "mode": "append"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(ExamSectionQuestion.objects.count(), 2)

    def test_blocks_can_be_removed_by_id(self):
        self.put([block.pk for block in self.blocks])

        self.client.delete(
            section_questions(self.section_row.pk),
            {"block_ids": [self.blocks[0].pk, self.blocks[1].pk]},
            content_type="application/json",
            **self.auth,
        )

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 3)


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

    def test_they_drop_when_a_pick_is_deleted_through_the_api(self):
        pick = self.pick()
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

        self.client.delete(detail("exam_section_question", pick.pk), **self.auth)

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
        """The cascade may remove the section before its picks; syncing a row
        that is about to disappear must not raise."""
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

        services.sync_section_totals(self.section_row)

        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 1)

    def test_the_exam_totals_do_not_fan_out_across_sections(self):
        """Three aggregates over one join. A second to-many annotation here
        would cross-product them and double every number."""
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
        """PROTECT plus the existing `ProtectedError` handler, so a used
        question answers 409 instead of silently shortening the exam."""
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

    def test_sections_that_do_not_fill_the_exam_block_publishing(self):
        """Each section adds up internally; together they fall short.

        Distinct from the mismatch above, where the section-level check fires
        first and the exam-level sum is never reached.
        """
        exam = self.exam(total_marks=100)
        self.fill(self.section(exam=exam, marks=30), 30)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 422)
        self.assertIn("not the exam's", str(response.json()["errors"]))

    def test_a_complete_exam_publishes(self):
        exam = self.exam(total_marks=30)
        self.fill(self.section(exam=exam, marks=30), 30)

        response = self.publish(exam)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "published")

    def test_answer_any_seven_of_eleven_publishes_at_seventy(self):
        """The standard CQ shape. Without `required_question_count` the section
        would compute 110 against a declared 70 and be refused."""
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
        """A paper is whatever its sections are, so one MCQ part is a complete
        paper -- there is no "mixed" declaration left to contradict."""
        exam = self.exam(total_marks=30)
        self.fill(self.section(exam=exam, marks=30), 30)

        self.assertEqual(self.publish(exam).status_code, 200)

    def test_an_exam_cannot_be_born_published(self):
        response = self.client.post(
            EXAMS_URL,
            {"title": "Instant", "total_marks": "30.00", "status": "published"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("status", response.json()["errors"])


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
        """Nothing auto-grades a creative answer, so nothing can detect a wrong
        one to penalise."""
        self.assert_refused("negative_marks", question_type="cq", marks_per_question="10.00", negative_marks="1.00")

    def test_a_blank_rate_round_trips_as_null(self):
        """The column is still nullable, but NULL and 0 now resolve alike.

        They used to differ -- NULL meant "use the paper's rate" -- and the
        paper no longer has one. Kept nullable so a blank form field is not
        forced to invent a number; `section_marking` reads both as zero.
        """
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
        """Only the *options* rule is type-bound -- which সৃজনশীল question is
        printed first is a choice either way."""
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
        """The serializer catches this first, so without an ORM-path test the
        constraint itself would never be exercised."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.section(marks_per_question=Decimal("1.00"), negative_marks=Decimal("2.00"))

    def test_the_database_refuses_a_pass_mark_above_the_section_marks(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.section(marks=Decimal("30.00"), pass_marks=Decimal("40.00"))

    def test_the_admin_form_path_runs_the_same_rules(self):
        """`ExamSection` had no `clean()`, so every one of these was bypassable
        from the Django admin."""
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
    """Negative marking is a property of the part, not of the paper.

    One exam's MCQ half and সৃজনশীল half are not penalised alike, so there is
    no paper-level rate to inherit and nothing to resolve between two columns.
    """

    def test_a_part_carries_its_own_rate(self):
        section = self.section(negative_marks=Decimal("0.25"))

        self.assertEqual(services.section_marking(section).negative, Decimal("0.25"))

    def test_a_part_that_sets_nothing_is_not_penalised(self):
        section = self.section()

        self.assertEqual(services.section_marking(section).negative, Decimal("0.00"))

    def test_an_explicit_zero_is_not_penalised_either(self):
        """NULL and 0 say the same thing now: nothing is subtracted."""
        section = self.section(negative_marks=Decimal("0.00"))

        self.assertEqual(services.section_marking(section).negative, Decimal("0.00"))

    def test_a_creative_part_is_never_negatively_marked(self):
        """Nothing can detect a wrong সৃজনশীল answer, so a rate typed onto one
        is still worth zero."""
        section = self.section(
            title="সৃজনশীল",
            question_type=ExamSection.Type.CQ,
            marks=70,
            marks_per_question=10,
            negative_marks=Decimal("0.25"),
        )

        self.assertEqual(services.section_marking(section).negative, Decimal("0.00"))

    def test_the_positive_rate_is_the_parts_own(self):
        section = self.section(marks=70, marks_per_question=Decimal("10.00"))

        self.assertEqual(services.section_marking(section).positive, Decimal("10.00"))

    def test_resolving_costs_no_query_when_the_exam_is_passed(self):
        exam = self.exam()
        section = self.section(exam=exam)

        with self.assertNumQueries(0):
            services.section_marking(section, exam=exam)


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
        """The paper's নির্দেশনা and a part's are different lines in different
        places -- "৬টি প্রশ্নের উত্তর দাও" belongs under the সৃজনশীল heading,
        not at the top of the page."""
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
        """Each part carries its own rate, and a সৃজনশীল one is worth zero
        however it was filled in -- nothing can mark a creative answer wrong."""
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
        """A half-built paper is the normal state in the builder, so the header
        says what the teacher wrote *and* what has actually been picked."""
        exam = self.exam(total_marks=30)
        section = self.section(exam=exam, marks=30)
        for _ in range(28):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)

        part = self.header(exam)["parts"][0]

        self.assertEqual(part["marks"], "30.00")
        self.assertEqual(part["computed_marks"], "28.00")
        self.assertTrue(part["problems"])

    def test_the_multiplication_is_hidden_when_it_would_not_add_up(self):
        """A pick may be repriced off the section rate, and then
        "১ ✕ 30 = 30" is simply false."""
        exam = self.exam(total_marks=31)
        section = self.section(exam=exam, marks=31)
        for _ in range(29):
            ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=1)
        ExamSectionQuestion.objects.create(section=section, block=self.mcq_block(), marks=2)

        part = self.header(exam)["parts"][0]

        self.assertFalse(part["shows_multiplication"])
        self.assertEqual(part["computed_marks"], "31.00")

    def test_its_problems_are_the_publish_errors_verbatim(self):
        """Two lists of "what is wrong with this paper" would drift in a week,
        so the header shows the sentences publish would refuse with."""
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
        """A raw Decimal renders as the float 1.0 while `total_marks` beside it
        is the string "1.00"."""
        exam = self.build_paper()
        body = self.client.get(detail("exam", exam.pk), **self.auth).json()

        self.assertIsInstance(body["total_marks"], str)
        self.assertIsInstance(body["paper"]["total_marks"], str)
        self.assertIsInstance(body["paper"]["parts"][0]["marks"], str)

    def test_the_list_carries_no_header(self):
        """It would need every section of every row, and the list is pinned at
        four queries."""
        self.build_paper()

        self.assertNotIn("paper", self.client.get(EXAMS_URL, **self.auth).json()["data"][0])


class PublishedPaperTests(ExamTestCase):
    """A published paper is frozen structurally, and only structurally.

    The publish check used to sit on the exam serializer alone, so a live exam
    could be gutted through the section and picker endpoints -- and then
    renaming it failed with an error about section marks, because every later
    PATCH re-ran the publish rules.
    """

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
            {"block_ids": [self.blocks[0].pk], "mode": "replace"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.section_row.refresh_from_db()
        self.assertEqual(self.section_row.question_count, 3)

    def test_a_question_cannot_be_added(self):
        response = self.client.post(
            PICKS_URL,
            {"section_id": self.section_row.pk, "block_id": self.mcq_block().pk},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)

    def test_a_question_cannot_be_dropped(self):
        pick = ExamSectionQuestion.objects.first()

        response = self.client.delete(detail("exam_section_question", pick.pk), **self.auth)

        self.assertEqual(response.status_code, 422)
        self.assertTrue(ExamSectionQuestion.objects.filter(pk=pick.pk).exists())

    def test_a_section_cannot_be_reworked_or_removed(self):
        # A value the section rules would otherwise accept -- 9 against a
        # 3-mark exam is refused by the sibling check, which would let this
        # pass for the wrong reason.
        response = self.patch("exam_section", self.section_row.pk, {"marks": "2"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("status", response.json()["errors"])
        self.assertEqual(self.client.delete(detail("exam_section", self.section_row.pk), **self.auth).status_code, 422)

    def test_its_total_marks_cannot_be_changed(self):
        response = self.patch("exam", self.exam_row.pk, {"total_marks": "9"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("total_marks", response.json()["errors"])

    def test_but_it_can_still_be_renamed_and_rescheduled(self):
        """The other half of the bug: every PATCH used to re-run the publish
        rules, so renaming a live exam failed with an error about its marks."""
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
        """The publish rules run on the transition, not on every later edit.

        They used to run whenever `status` was `published`, so renaming a paper
        whose marks had drifted failed with an error about section marks — a
        field the request never mentioned. The API can no longer break a live
        paper, so this reaches past it and edits the rows directly.
        """
        ExamSectionQuestion.objects.filter(section=self.section_row).first().delete()

        response = self.patch("exam", self.exam_row.pk, {"title": "Renamed anyway"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["title"], "Renamed anyway")

    def test_the_django_admin_cannot_break_a_published_paper_either(self):
        """`clean()` is the admin's only guard, and it ran the section rules
        without ever asking whether the paper was live."""
        # Re-fetched, not refreshed: `refresh_from_db` leaves the cached `exam`
        # holding the draft status it was published out of.
        section = ExamSection.objects.select_related("exam").get(pk=self.section_row.pk)
        section.marks = Decimal("2.00")

        with self.assertRaises(ValidationError):
            section.clean()

    def test_archiving_is_how_an_exam_is_retired(self):
        """`is_active` used to sit beside `status` saying the same thing, with
        no rule about which won."""
        response = self.patch("exam", self.exam_row.pk, {"status": "archived"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "archived")


class ExamOwnershipTests(ExamTestCase):
    def setUp(self):
        super().setUp()
        self.mine = self.exam(title="Mine", created_by=self.teacher)
        self.theirs = self.exam(title="Theirs", created_by=self.other_teacher)

    def test_a_teacher_lists_only_their_own_exams(self):
        body = self.client.get(EXAMS_URL, **self.teacher_auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [self.mine.pk])

    def test_an_admin_lists_every_exam(self):
        body = self.client.get(EXAMS_URL, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 2)

    def test_a_teacher_cannot_open_another_teachers_exam_by_id(self):
        """The queryset filter hides it from the list; this is what stops it
        being fetched directly, which the filter alone would allow."""
        response = self.client.get(detail("exam", self.theirs.pk), **self.teacher_auth)

        self.assertIn(response.status_code, (403, 404))

    def test_a_teacher_cannot_edit_another_teachers_exam(self):
        response = self.client.patch(
            detail("exam", self.theirs.pk),
            {"title": "Hijacked"},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertIn(response.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, "Theirs")

    def test_a_teacher_cannot_hang_a_section_off_another_teachers_exam(self):
        """DRF runs no object permission on a POST to a child collection, so
        the queryset filter and `has_object_permission` both miss this."""
        response = self.client.post(
            SECTIONS_URL,
            {
                "exam_id": self.theirs.pk,
                "title": "Sneaked in",
                "question_type": "mcq",
                "subject_id": self.ict.pk,
                "marks": "30.00",
            },
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.theirs.sections.count(), 0)

    def test_a_teacher_cannot_bulk_pick_into_another_teachers_section(self):
        """A plain `APIView` fetches its own row, so DRF runs no object
        permission there either."""
        section = self.section(exam=self.theirs)

        response = self.client.put(
            section_questions(section.pk),
            {"block_ids": [self.mcq_block().pk]},
            content_type="application/json",
            **self.teacher_auth,
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ExamSectionQuestion.objects.count(), 0)

    def test_the_object_guard_refuses_on_its_own(self):
        """Asserted against the permission class directly, not through a view.

        Via the API the queryset filter already hides another teacher's exam,
        so a 404 comes back whether or not the object guard exists -- a test
        that accepts (403, 404) passes with the guard deleted. The two halves
        are defence in depth, and this is what pins the second one.
        """
        view = SimpleNamespace(author_id_for=lambda obj: obj.created_by_id)
        guard = IsExamAuthor()

        mine = SimpleNamespace(user=self.teacher)
        self.assertTrue(guard.has_object_permission(mine, view, self.mine))
        self.assertFalse(guard.has_object_permission(mine, view, self.theirs))

        # An admin passes everything, including an orphaned exam.
        as_admin = SimpleNamespace(user=self.admin)
        self.assertTrue(guard.has_object_permission(as_admin, view, self.theirs))

        # A NULL author matches nobody rather than everybody.
        self.theirs.created_by = None
        self.assertFalse(guard.has_object_permission(mine, view, self.theirs))

    def test_an_orphaned_exam_falls_to_admins_not_to_everyone(self):
        """`created_by` is SET_NULL, so a deleted author leaves NULL -- which
        matches no teacher's filter."""
        Exam.objects.filter(pk=self.mine.pk).update(created_by=None)

        self.assertEqual(self.client.get(EXAMS_URL, **self.teacher_auth).json()["meta"]["total"], 0)
        self.assertEqual(self.client.get(EXAMS_URL, **self.auth).json()["meta"]["total"], 2)

    def test_deleting_a_teacher_does_not_take_their_exams_with_them(self):
        self.other_teacher.delete()

        self.assertTrue(Exam.objects.filter(pk=self.theirs.pk).exists())


class PermissionTests(ExamTestCase):
    """Exam payloads reach the answer key through the picker, so they are
    teaching staff only."""

    def setUp(self):
        super().setUp()
        self.row = self.section()

    def _urls(self):
        return [
            EXAMS_URL,
            SECTIONS_URL,
            PICKS_URL,
            detail("exam", self.row.exam_id),
            detail("exam_section", self.row.pk),
            section_questions(self.row.pk),
        ]

    def test_a_student_is_refused(self):
        auth = self._auth(self._user("01810002222", User.Role.STUDENT))
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_a_moderator_is_refused(self):
        """The notices desk has no business in the question bank."""
        auth = self._auth(self._user("01810003333", User.Role.MODERATOR))
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        """The project default is `IsAuthenticatedOrReadOnly`, so a view that
        forgets `permission_classes` would serve these to anyone."""
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 401, url)


class PassageOnAPaperTests(ExamTestCase):
    """A passage (উদ্দীপক) with several MCQs under it.

    The block model already carries this -- `kind` (structure) and
    `question_type` (content) are orthogonal -- so these pin the two things
    that are *not* free: what such a block counts and costs, and that nothing
    can take it apart.
    """

    def setUp(self):
        super().setUp()
        self.mcq_section = self.section(marks=25, marks_per_question=1)

    def place(self, section, block):
        """Place a block the way the picker prices it.

        `refresh_from_db` because `question_count` is written by the question
        app's signals, so an instance built in this process is stale.
        """
        block.refresh_from_db()
        count = services.block_question_count(block, section.question_type)
        return ExamSectionQuestion.objects.create(
            section=section, block=block, marks=count * section.marks_per_question
        )

    def test_a_passage_of_mcqs_is_admissible_to_an_mcq_section(self):
        """`kind` is structure, `question_type` is content -- a group of MCQs is
        MCQ content and belongs on an MCQ paper."""
        passage = self.mcq_passage(parts=3)

        services.validate_section_blocks(section=self.mcq_section, blocks=[passage])

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
            {"block_ids": [passage.pk], "mode": "replace"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        pick = ExamSectionQuestion.objects.get(section=self.mcq_section, block=passage)
        self.assertEqual(pick.marks, Decimal("3.00"))


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
        return [pick.pk for pick in services.shuffled_picks(picks, seed=seed)]

    def test_it_loses_nothing_and_invents_nothing(self):
        shuffled = self.ordered(services.paper_seed(exam_id=1, user_id=7))

        self.assertCountEqual(shuffled, [pick.pk for pick in self.picks])

    def test_the_same_student_gets_the_same_paper_twice(self):
        seed = services.paper_seed(exam_id=1, user_id=7)

        self.assertEqual(self.ordered(seed), self.ordered(seed))

    def test_a_different_student_gets_a_different_paper(self):
        mine = self.ordered(services.paper_seed(exam_id=1, user_id=7))
        theirs = self.ordered(services.paper_seed(exam_id=1, user_id=8))

        self.assertNotEqual(mine, theirs)

    def test_the_seed_does_not_move_between_processes(self):
        """`hash()` is salted per process; this must not be."""
        self.assertEqual(
            services.paper_seed(exam_id=1, user_id=7),
            services.paper_seed(exam_id=1, user_id=7),
        )
        self.assertNotEqual(
            services.paper_seed(exam_id=1, user_id=7),
            services.paper_seed(exam_id=2, user_id=7),
        )

    def test_a_passage_is_never_taken_apart(self):
        """The whole reason shuffling is safe: the unit being permuted is the
        block, so the passage and its questions move together."""
        passage = self.mcq_passage(parts=3)
        ExamSectionQuestion.objects.create(section=self.section_row, block=passage, marks=3, order=6)

        shuffled = services.shuffled_picks(
            self.section_row.section_questions.order_by("order", "id"), seed=services.paper_seed(exam_id=1, user_id=7)
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

        shuffled = services.shuffled_options(options, seed=services.paper_seed(exam_id=1, user_id=7))

        self.assertCountEqual(shuffled, options)
        self.assertIsNot(shuffled, options, "the caller's list was mutated")


class SectionBlocksRelationTests(ExamTestCase):
    """`ExamSection.blocks` is the same rows as `section_questions`.

    Declared `through` the pick model, so it reads as "a section has blocks"
    without giving up the column the paper's order lives in.
    """

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
        """Why the plain M2M would not have done.

        `blocks` carries `QuestionBlock`'s own ordering; only the pick knows
        which question is printed first.
        """
        section = self.section()
        first, second = self.mcq_block(), self.mcq_block()
        # Picked in the reverse of the bank's order.
        ExamSectionQuestion.objects.create(section=section, block=second, order=0)
        ExamSectionQuestion.objects.create(section=section, block=first, order=1)

        on_the_paper = list(section.section_questions.order_by("order", "id").values_list("block_id", flat=True))
        self.assertEqual(on_the_paper, [second.pk, first.pk])
        self.assertEqual(list(section.blocks.values_list("pk", flat=True)), [first.pk, second.pk])

    def test_writing_through_the_m2m_is_the_trap_the_docstring_warns_about(self):
        """Pins why `blocks` is read-only by convention rather than by Django.

        Both extra columns on the pick have defaults, so `.add()` is permitted
        instead of refused -- and it is wrong twice: everything added in one
        call shares `order = 0`, and `.add()` uses `bulk_create`, which skips
        the signals that keep the counters true.
        """
        section = self.section()
        first, second = self.mcq_block(), self.mcq_block()

        section.blocks.add(first, second)

        self.assertEqual([pick.order for pick in section.section_questions.all()], [0, 0])
        section.refresh_from_db()
        self.assertEqual(section.question_count, 0)
        self.assertEqual(section.computed_marks, 0)

        # What the picker does instead keeps both true.
        services.sync_section_totals(section)
        section.refresh_from_db()
        self.assertEqual(section.question_count, 2)


class SchemaEnumNamingTests(TestCase):
    """Every enum in the public schema is named after what it is.

    Several models field-name `status` or `type` over different choice sets.
    Left alone, drf-spectacular cannot name such an enum after any one
    component and falls back to a hash -- `Status91dEnum`, `Type109Enum` --
    which is what a generated client then carries. The names are pinned in
    `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` by *string*, so a model or
    module rename breaks them without breaking any import and without failing
    a build. These tests are the thing that notices.
    """

    def schema(self):
        from drf_spectacular.generators import SchemaGenerator

        return SchemaGenerator().get_schema(request=None, public=True)

    def test_every_override_still_resolves(self):
        from django.conf import settings

        from drf_spectacular.plumbing import deep_import_string

        overrides = settings.SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]

        self.assertTrue(overrides, "the overrides went missing entirely")
        for name, path in overrides.items():
            with self.subTest(enum=name):
                self.assertIsNotNone(deep_import_string(path), f"{name} points at {path}, which no longer exists")

    def test_no_enum_is_named_after_a_hash(self):
        """The failure this guards is silent -- the schema builds either way."""
        names = [n for n in self.schema()["components"]["schemas"] if n.endswith("Enum")]

        hashed = [n for n in names if any(character.isdigit() for character in n)]
        self.assertEqual(hashed, [], "drf-spectacular fell back to hashing a colliding enum name")

    def test_the_colliding_enums_keep_their_names(self):
        components = self.schema()["components"]["schemas"]

        self.assertEqual(
            components["AdminExam"]["properties"]["status"]["$ref"],
            "#/components/schemas/ExamStatusEnum",
        )
        self.assertEqual(components["ExamStatusEnum"]["enum"], [v for v, _ in Exam.Status.choices])
        self.assertEqual(components["PaymentStatusEnum"]["enum"], ["pending", "successful", "failed"])
        self.assertEqual(components["ContentTypeEnum"]["enum"], ["video", "note", "pdf", "exam", "link", "live"])

    def test_one_choice_set_carries_one_name(self):
        """`Coupon.discount_type` and `Product.coupon_discount_type` are
        separate TextChoices with identical values, so they are one enum to the
        schema -- and used to be published under two names."""
        components = self.schema()["components"]["schemas"]

        named = {n for n, c in components.items() if isinstance(c, dict) and c.get("enum") == ["percent", "fixed"]}
        self.assertEqual(named, {"DiscountTypeEnum"})


class ExamListOrderingTests(ExamTestCase):
    """The list is paginated, so it has to be ordered.

    `Meta.ordering` alone is not enough here: `exam_queryset` annotates
    aggregates, which sets a GROUP BY, and Django drops the model's default
    ordering from the SQL when it does. The page then came back in whatever
    order the database chose, so a row could appear on two pages or on none.
    """

    def test_the_queryset_is_ordered(self):
        self.assertTrue(exam_queryset().ordered)
        self.assertIn("ORDER BY", str(exam_queryset().query))

    def test_the_page_is_newest_first(self):
        for title in ("First", "Second", "Third"):
            self.exam(title=title)

        response = self.client.get(EXAMS_URL, **self.auth)

        titles = [row["title"] for row in response.json()["data"]]
        self.assertEqual(titles, sorted(titles, key=lambda t: ["Third", "Second", "First"].index(t)))
        self.assertEqual(titles[0], "Third")


class ExamListQueryBudgetTests(ExamTestCase):
    def build(self, exams):
        for index in range(exams):
            exam = self.exam(title=f"Paper {index}")
            for title in ("MCQ", "সৃজনশীল"):
                section = self.section(exam=exam, title=title)
                for _ in range(3):
                    ExamSectionQuestion.objects.create(section=section, block=self.mcq_block())

    def test_the_page_costs_a_fixed_number_of_queries(self):
        self.build(6)

        # token, role groups, count, exams (the three annotations ride the one
        # `sections` join), plus one light prefetch of the section types
        with self.assertNumQueries(5):
            self.client.get(EXAMS_URL, **self.auth)

    def test_the_cost_does_not_move_with_the_fixture(self):
        """What turns "fast on my laptop" into "not per-row"."""
        self.build(12)

        with self.assertNumQueries(5):
            self.client.get(EXAMS_URL, **self.auth)

    def test_the_detail_tree_costs_a_fixed_number_of_queries(self):
        """Three sections, not one: the paper header walks them, and a
        per-section query would read as 8 rather than hide inside 5."""
        self.build(1)
        exam = Exam.objects.first()
        for title in ("Third", "Fourth"):
            self.section(exam=exam, title=title, marks=1)

        # token, role groups, exam, sections, picks
        with self.assertNumQueries(5):
            self.client.get(detail("exam", exam.pk), **self.auth)
