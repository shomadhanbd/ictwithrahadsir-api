"""The question bank: ownership, ordering, authoring rules and the admin API."""

from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.academic.models import Chapter, ClassLevel, Group, Subject, Topic
from apps.identity.models import User
from apps.question import services
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet, QuestionSource

BLOCKS_URL = reverse("api:question:admin_question_block_list")
QUESTIONS_URL = reverse("api:question:admin_question_list")
SOURCES_URL = reverse("api:question:admin_question_source_list")


def detail(resource, pk):
    return reverse(f"api:question:admin_{resource}_detail", args=[pk])


class QuestionTestCase(TestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone="01700001111", name="Admin", password="Str0ngPass!23", role=User.Role.ADMIN
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=admin).key}"}

        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc")
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(name="Number Systems", subject=self.ict, chapter_number=1)

    def block(self, **overrides):
        return QuestionBlock.objects.create(**{"subject": self.ict, "chapter": self.chapter, **overrides})


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


class OrderingTests(QuestionTestCase):
    def test_a_group_returns_its_questions_in_order(self):
        """Without `Meta.ordering` the database picks, so a creative question's
        ক/খ/গ/ঘ arrive shuffled. This is the reference app's A2."""
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


class AuthoringRuleTests(QuestionTestCase):
    def _post_question(self, **overrides):
        payload = {
            "block_id": self.block().pk,
            "question_type": "mcq",
            "prompt_content": "2 + 2 = ?",
            "options": [
                {"content": "4", "is_correct": True, "position": 0},
                {"content": "5", "is_correct": False, "position": 1},
            ],
            **overrides,
        }
        return self.client.post(QUESTIONS_URL, payload, content_type="application/json", **self.auth)

    def test_a_valid_mcq_is_accepted(self):
        response = self._post_question()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["options"]), 2)

    def test_an_mcq_needs_a_correct_option(self):
        """Otherwise an empty answer compares equal to an empty correct-set and
        scores full marks -- the reference app's A5."""
        response = self._post_question(
            options=[
                {"content": "4", "is_correct": False, "position": 0},
                {"content": "5", "is_correct": False, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("options", response.json()["errors"])

    def test_a_single_answer_mcq_cannot_have_two_correct_options(self):
        response = self._post_question(
            options=[
                {"content": "4", "is_correct": True, "position": 0},
                {"content": "5", "is_correct": True, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 422)

    def test_a_multiple_answer_mcq_can(self):
        response = self._post_question(
            metadata={"select_mode": "multiple"},
            options=[
                {"content": "4", "is_correct": True, "position": 0},
                {"content": "5", "is_correct": True, "position": 1},
            ],
        )

        self.assertEqual(response.status_code, 201)

    def test_a_cq_needs_no_options(self):
        response = self._post_question(question_type="cq", options=[])
        self.assertEqual(response.status_code, 201)

    def test_a_question_needs_exactly_one_owner(self):
        for payload in ({}, {"question_set_id": None}):
            response = self.client.post(
                QUESTIONS_URL,
                {"question_type": "cq", "prompt_content": "?", **payload},
                content_type="application/json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 422)

    def test_a_chapter_from_another_subject_is_refused(self):
        other = Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science, slug="phy-hsc-science")
        elsewhere = Chapter.objects.create(name="Motion", subject=other)

        response = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "chapter_id": elsewhere.pk},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("chapter", response.json()["errors"])

    def test_a_group_block_refuses_a_standalone_question(self):
        block = self.block(kind=QuestionBlock.Kind.STANDALONE)
        Question.objects.create(block=block, prompt_content="?")

        response = self.client.patch(
            detail("question_block", block.pk),
            {"kind": "group"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("kind", response.json()["errors"])


class QuestionCountTests(QuestionTestCase):
    """Maintained on write, not by a backfill script -- the reference app's B1."""

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
        """`destroy()` never touches the serializer, so a count maintained there
        only ever went up."""
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
        """The cascade deletes the questions first; syncing a block that is
        about to disappear must not raise."""
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


class PartialUpdateTests(QuestionTestCase):
    """An edit is validated against what the question will end up with."""

    def setUp(self):
        super().setUp()
        self.question = Question.objects.create(block=self.block(), prompt_content="2 + 2 = ?")
        QuestionOption.objects.create(question=self.question, content="4", is_correct=True, position=0)
        QuestionOption.objects.create(question=self.question, content="5", is_correct=False, position=1)

    def patch(self, payload):
        return self.client.patch(
            detail("question", self.question.pk), payload, content_type="application/json", **self.auth
        )

    def test_editing_only_the_prompt_keeps_the_existing_answer_key(self):
        """The MCQ guard used to read the options off the request, which a PATCH
        that only touches the prompt does not carry -- so it refused the edit
        for having no correct option, over data the request never proposed to
        change."""
        response = self.patch({"prompt_content": "2 + 2 = কত?"})

        self.assertEqual(response.status_code, 200)
        self.question.refresh_from_db()
        self.assertEqual(self.question.prompt_content, "2 + 2 = কত?")

    def test_an_edit_that_would_break_the_answer_key_is_still_refused(self):
        response = self.patch({"options": [{"content": "4", "is_correct": False, "position": 0}]})

        self.assertEqual(response.status_code, 422)

    def test_switching_to_multiple_is_checked_against_the_stored_options(self):
        """No options in the request, so the two already stored are what the
        rule has to judge."""
        self.question.options.update(is_correct=True)

        response = self.patch({"metadata": {"select_mode": "single"}})

        self.assertEqual(response.status_code, 422)


class OptionIdentityTests(QuestionTestCase):
    """Options keep their ids across an edit.

    Nothing reads them yet; a submission's `selected_option` will, and by then
    a churned id means an answer pointing at a row that no longer exists.
    """

    def setUp(self):
        super().setUp()
        self.question = Question.objects.create(block=self.block(), prompt_content="?")
        self.first = QuestionOption.objects.create(question=self.question, content="4", is_correct=True, position=0)
        self.second = QuestionOption.objects.create(question=self.question, content="5", is_correct=False, position=1)

    def patch(self, options):
        return self.client.patch(
            detail("question", self.question.pk),
            {"options": options},
            content_type="application/json",
            **self.auth,
        )

    def test_an_edited_option_keeps_its_id(self):
        response = self.patch(
            [
                {"id": self.first.pk, "content": "চার", "is_correct": True, "position": 0},
                {"id": self.second.pk, "content": "5", "is_correct": False, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([o["id"] for o in response.json()["options"]], [self.first.pk, self.second.pk])
        self.first.refresh_from_db()
        self.assertEqual(self.first.content, "চার")

    def test_an_option_left_out_is_removed_and_a_new_one_is_added(self):
        response = self.patch(
            [
                {"id": self.first.pk, "content": "4", "is_correct": True, "position": 0},
                {"content": "6", "is_correct": False, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuestionOption.objects.filter(pk=self.second.pk).exists())
        self.assertEqual(self.question.options.count(), 2)

    def test_two_options_can_swap_positions(self):
        """`(question, position)` is unique and checked per statement, so the
        swap only survives because the rows are parked out of the way first."""
        response = self.patch(
            [
                {"id": self.first.pk, "content": "4", "is_correct": True, "position": 1},
                {"id": self.second.pk, "content": "5", "is_correct": False, "position": 0},
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual((self.first.position, self.second.position), (1, 0))

    def test_an_unknown_id_is_treated_as_a_new_option(self):
        response = self.patch(
            [
                {"id": self.first.pk, "content": "4", "is_correct": True, "position": 0},
                {"id": 9999, "content": "7", "is_correct": False, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuestionOption.objects.filter(pk=9999).exists())
        self.assertEqual(self.question.options.count(), 2)


class BlockKindTests(QuestionTestCase):
    """`kind` and what hangs off the block have to agree, whichever is written first."""

    def test_a_stimulus_set_is_refused_on_a_standalone_block(self):
        """The block serializer could only check this when the *block* was
        saved, and a set is attached afterwards -- so a standalone block with a
        stimulus set went straight through."""
        with self.assertRaises(ValidationError):
            QuestionSet(block=self.block(), stimulus_content="উদ্দীপক").clean()

    def test_a_stimulus_set_is_accepted_on_a_group_block(self):
        QuestionSet(block=self.block(kind=QuestionBlock.Kind.GROUP), stimulus_content="উদ্দীপক").clean()

    def test_a_question_cannot_hang_directly_off_a_group_block(self):
        response = self.client.post(
            QUESTIONS_URL,
            {
                "block_id": self.block(kind=QuestionBlock.Kind.GROUP).pk,
                "question_type": "cq",
                "prompt_content": "?",
            },
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("block_id", response.json()["errors"])

    def test_a_question_cannot_join_a_set_hanging_off_a_standalone_block(self):
        # Built through the ORM, which is exactly the path that produced the
        # contradiction in the first place.
        question_set = QuestionSet.objects.create(block=self.block(), stimulus_content="উদ্দীপক")

        response = self.client.post(
            QUESTIONS_URL,
            {"question_set_id": question_set.pk, "question_type": "cq", "prompt_content": "?"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("question_set_id", response.json()["errors"])

    def test_the_admin_form_path_refuses_it_too(self):
        with self.assertRaises(ValidationError):
            Question(block=self.block(kind=QuestionBlock.Kind.GROUP), prompt_content="?").clean()


class FeedTests(QuestionTestCase):
    def setUp(self):
        super().setUp()
        self.group_block = self.block(kind=QuestionBlock.Kind.GROUP, order_in_chapter=0)
        question_set = QuestionSet.objects.create(
            block=self.group_block, stimulus_content="উদ্দীপক", stimulus_type="text"
        )
        for order in range(2):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.CQ,
                order_in_set=order,
                prompt_content=f"part {order}",
            )

        self.solo = self.block(order_in_chapter=1)
        question = Question.objects.create(block=self.solo, prompt_content="2 + 2 = ?")
        QuestionOption.objects.create(question=question, content="4", is_correct=True, position=0)

    def test_a_block_carries_its_whole_tree(self):
        rows = {row["id"]: row for row in self.client.get(BLOCKS_URL, **self.auth).json()["data"]}

        grouped = rows[self.group_block.pk]
        self.assertEqual(len(grouped["question_set"]["questions"]), 2)
        self.assertIsNone(grouped["standalone_question"])

        solo = rows[self.solo.pk]
        self.assertIsNone(solo["question_set"])
        self.assertEqual(len(solo["standalone_question"]["options"]), 1)

    def test_the_page_costs_a_fixed_number_of_queries(self):
        """The nested tree is where an N+1 would hide."""
        for order in range(2, 8):
            block = self.block(order_in_chapter=order)
            Question.objects.create(block=block, prompt_content="?")

        # token, role groups, count, blocks, topics, sources, sets, grouped,
        # standalone, options x2
        with self.assertNumQueries(11):
            self.client.get(BLOCKS_URL, **self.auth)

    def test_search_reaches_a_question_inside_a_group(self):
        """Only the stimulus and the standalone prompt were searched, so every
        question inside a group -- the bulk of the bank -- was unfindable."""
        body = self.client.get(BLOCKS_URL, {"search": "part 1"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["id"], self.group_block.pk)

    def test_a_block_matching_twice_is_listed_once(self):
        """Searching a to-many path fans the join out; without DISTINCT the
        same block comes back per matching question."""
        body = self.client.get(BLOCKS_URL, {"search": "part"}, **self.auth).json()

        ids = [block["id"] for block in body["data"]]
        self.assertEqual(ids, [self.group_block.pk])
        self.assertEqual(body["meta"]["total"], 1)

    def test_the_list_can_be_scoped(self):
        body = self.client.get(BLOCKS_URL, {"kind": "group"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["id"], self.group_block.pk)


class ProvenanceTests(QuestionTestCase):
    """A question appears in many exams, so provenance is rows, not three columns."""

    def setUp(self):
        super().setUp()
        self.dhaka_2019 = QuestionSource.objects.create(name="ঢাকা বোর্ড", year=2019)
        self.rajshahi_2021 = QuestionSource.objects.create(name="রাজশাহী বোর্ড", year=2021)

    def test_one_block_can_carry_several_exams(self):
        """The whole point: three flat columns could record exactly one."""
        block = self.block()
        block.sources.set([self.dhaka_2019, self.rajshahi_2021])

        body = self.client.get(detail("question_block", block.pk), **self.auth).json()

        self.assertEqual(
            sorted(source["name"] for source in body["sources"]),
            ["ঢাকা বোর্ড", "রাজশাহী বোর্ড"],
        )

    def test_one_exam_is_shared_by_every_block_that_used_it(self):
        first, second = self.block(), self.block(order_in_chapter=1)
        first.sources.add(self.dhaka_2019)
        second.sources.add(self.dhaka_2019)

        self.assertEqual(self.dhaka_2019.question_blocks.count(), 2)

    def test_a_block_is_authored_with_its_sources(self):
        response = self.client.post(
            BLOCKS_URL,
            {
                "subject_id": self.ict.pk,
                "chapter_id": self.chapter.pk,
                "kind": "standalone",
                "source_ids": [self.dhaka_2019.pk, self.rajshahi_2021.pk],
            },
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["sources"]), 2)

    def test_the_feed_can_be_filtered_to_one_exam(self):
        """The filter that a JSONField could not serve: `__contains` is
        unsupported on SQLite, so this would not work in dev or here."""
        wanted = self.block()
        wanted.sources.add(self.dhaka_2019)
        self.block(order_in_chapter=1).sources.add(self.rajshahi_2021)

        body = self.client.get(BLOCKS_URL, {"source": self.dhaka_2019.pk}, **self.auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [wanted.pk])

    def test_the_feed_can_be_filtered_by_year(self):
        wanted = self.block()
        wanted.sources.add(self.dhaka_2019)
        self.block(order_in_chapter=1).sources.add(self.rajshahi_2021)

        body = self.client.get(BLOCKS_URL, {"source_year": 2019}, **self.auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [wanted.pk])

    def test_provenance_filters_must_describe_the_same_exam(self):
        """A block has many sources, so a separate `.filter()` per parameter
        opens a JOIN each and they match different rows -- this block would come
        back for "ঢাকা বোর্ড" + "2021", a paper that never existed."""
        block = self.block()
        block.sources.set([self.dhaka_2019, self.rajshahi_2021])

        body = self.client.get(
            BLOCKS_URL,
            {"source": self.dhaka_2019.pk, "source_year": 2021},
            **self.auth,
        ).json()

        self.assertEqual(body["data"], [])

    def test_the_same_exam_on_both_parameters_still_matches(self):
        block = self.block()
        block.sources.set([self.dhaka_2019, self.rajshahi_2021])

        body = self.client.get(
            BLOCKS_URL,
            {"source": self.dhaka_2019.pk, "source_year": 2019},
            **self.auth,
        ).json()

        self.assertEqual([row["id"] for row in body["data"]], [block.pk])

    def test_a_block_with_two_matching_papers_is_listed_once(self):
        block = self.block()
        block.sources.set([self.dhaka_2019, QuestionSource.objects.create(name="যশোর বোর্ড", year=2019)])

        body = self.client.get(BLOCKS_URL, {"source_year": 2019}, **self.auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [block.pk])

    def test_the_feed_can_be_filtered_by_kind(self):
        college = QuestionSource.objects.create(name="নটর ডেম কলেজ", kind=QuestionSource.Kind.COLLEGE, year=2022)
        wanted = self.block()
        wanted.sources.add(college)
        self.block(order_in_chapter=1).sources.add(self.dhaka_2019)

        body = self.client.get(BLOCKS_URL, {"source_kind": "college"}, **self.auth).json()

        self.assertEqual([row["id"] for row in body["data"]], [wanted.pk])

    def test_the_same_exam_cannot_be_recorded_twice(self):
        response = self.client.post(
            SOURCES_URL,
            {"kind": "board", "name": "ঢাকা বোর্ড", "year": 2019},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("name", response.json()["errors"])

    def test_an_undated_exam_cannot_be_recorded_twice_either(self):
        """NULL never equals NULL, so the four-column constraint lets undated
        rows duplicate; the partial constraint is what stops them."""
        QuestionSource.objects.create(name="নটর ডেম কলেজ", kind=QuestionSource.Kind.COLLEGE)

        response = self.client.post(
            SOURCES_URL,
            {"kind": "college", "name": "নটর ডেম কলেজ"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)

    def test_the_database_refuses_a_duplicate_exam(self):
        """The serializer catches this first, so without a test on the ORM path
        the constraint itself would never be exercised."""
        with self.assertRaises(IntegrityError), transaction.atomic():
            QuestionSource.objects.create(name="ঢাকা বোর্ড", year=2019)

    def test_the_database_refuses_a_duplicate_undated_exam(self):
        QuestionSource.objects.create(name="কুমিল্লা বোর্ড")

        with self.assertRaises(IntegrityError), transaction.atomic():
            QuestionSource.objects.create(name="কুমিল্লা বোর্ড")

    def test_the_same_board_in_another_year_is_a_different_exam(self):
        response = self.client.post(
            SOURCES_URL,
            {"kind": "board", "name": "ঢাকা বোর্ড", "year": 2022},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 201)

    def test_a_source_is_slugged_from_its_whole_label(self):
        """The year is part of the slug -- two years of one board must not
        collide."""
        unit = QuestionSource.objects.create(
            name="ঢাকা বিশ্ববিদ্যালয়", kind=QuestionSource.Kind.UNIVERSITY, unit="ka", year=2021
        )

        self.assertNotEqual(unit.slug, self.dhaka_2019.slug)
        self.assertTrue(unit.slug)
        self.assertIn("2021", unit.slug)

    def test_the_label_reads_as_one_exam(self):
        source = QuestionSource.objects.create(name="DU", kind=QuestionSource.Kind.UNIVERSITY, unit="ka", year=2021)

        self.assertEqual(source.label, "DU ka unit 2021")


class StimulusAuthoringTests(QuestionTestCase):
    """Creative questions are authored through the block that owns them.

    The stimulus was read-only with no endpoint of its own, so a group block
    could be created but never given its উদ্দীপক -- which meant CQ content could
    not be authored through the API at all.
    """

    def create(self, **overrides):
        payload = {"subject_id": self.ict.pk, "kind": "group", **overrides}
        return self.client.post(BLOCKS_URL, payload, content_type="application/json", **self.auth)

    def test_a_group_block_is_created_with_its_stimulus(self):
        response = self.create(question_set={"stimulus_content": "উদ্দীপক", "stimulus_type": "text"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["question_set"]["stimulus_content"], "উদ্দীপক")

    def test_its_parts_can_then_be_attached(self):
        block = self.create(question_set={"stimulus_content": "উদ্দীপক"}).json()

        part = self.client.post(
            QUESTIONS_URL,
            {
                "question_set_id": block["question_set"]["id"],
                "question_type": "cq",
                "label": "ক",
                "prompt_content": "part ক",
            },
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(part.status_code, 201)

    def test_editing_the_stimulus_keeps_its_parts(self):
        """Replacing the row instead of editing it would cascade every ক/খ/গ/ঘ
        away, because the parts hang off the stimulus."""
        block = self.create(question_set={"stimulus_content": "উদ্দীপক"}).json()
        Question.objects.create(
            question_set_id=block["question_set"]["id"],
            question_type=Question.Type.CQ,
            prompt_content="part ক",
        )

        response = self.client.patch(
            detail("question_block", block["id"]),
            {"question_set": {"stimulus_content": "edited"}},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["question_set"]["stimulus_content"], "edited")
        self.assertEqual(len(response.json()["question_set"]["questions"]), 1)

    def test_a_standalone_block_cannot_be_given_a_stimulus(self):
        """The `kind` rule, from the create side -- checking only the stored
        row let this through in the same request that made the block."""
        response = self.create(kind="standalone", question_set={"stimulus_content": "nope"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("kind", response.json()["errors"])


class QuestionTypeRegistryTests(QuestionTestCase):
    """Adding a question type should be a registry entry, not a new `if`."""

    def post(self, **overrides):
        payload = {
            "block_id": self.block().pk,
            "question_type": "mcq",
            "prompt_content": "?",
            "options": [
                {"content": "4", "is_correct": True, "position": 0},
                {"content": "5", "is_correct": False, "position": 1},
            ],
            **overrides,
        }
        return self.client.post(QUESTIONS_URL, payload, content_type="application/json", **self.auth)

    def test_a_types_settings_are_stored_normalised(self):
        """A client that omits the setting gets the declared default, not an
        empty dict that nothing downstream can read."""
        body = self.post().json()

        self.assertEqual(body["metadata"], {"select_mode": "single"})

    def test_a_setting_the_type_does_not_have_is_refused(self):
        """A typo that silently persists is how a setting comes to exist in the
        database and nowhere in the code."""
        response = self.post(metadata={"shuffle": True})

        self.assertEqual(response.status_code, 422)
        self.assertIn("metadata", response.json()["errors"])

    def test_a_setting_outside_its_choices_is_refused(self):
        response = self.post(metadata={"select_mode": "sometimes"})

        self.assertEqual(response.status_code, 422)

    def test_a_type_with_no_options_refuses_them(self):
        """Declared by the registry (`uses_options`), not by naming CQ here."""
        response = self.post(question_type="cq", metadata={})

        self.assertEqual(response.status_code, 422)
        self.assertIn("options", response.json()["errors"])

    def test_a_creative_question_carries_no_settings(self):
        response = self.post(question_type="cq", options=[])

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["metadata"], {})

    def test_the_model_and_the_registry_cannot_drift(self):
        from apps.question import types

        self.assertEqual(sorted(types.REGISTRY), sorted(Question.Type.values))


class QuestionTypeFilterTests(QuestionTestCase):
    """The exam picker's main call: narrow the bank to one question type."""

    def setUp(self):
        super().setUp()
        self.mcq = self.block()
        Question.objects.create(block=self.mcq, question_type=Question.Type.MCQ, prompt_content="?")

        self.cq = self.block(kind=QuestionBlock.Kind.GROUP, order_in_chapter=1)
        cq_set = QuestionSet.objects.create(block=self.cq, stimulus_content="উদ্দীপক")
        for label in ("ক", "খ"):
            Question.objects.create(
                question_set=cq_set, question_type=Question.Type.CQ, label=label, prompt_content=label
            )

        self.mixed = self.block(kind=QuestionBlock.Kind.GROUP, order_in_chapter=2)
        mixed_set = QuestionSet.objects.create(block=self.mixed, stimulus_content="mixed")
        Question.objects.create(question_set=mixed_set, question_type=Question.Type.CQ, prompt_content="cq part")
        Question.objects.create(question_set=mixed_set, question_type=Question.Type.MCQ, prompt_content="mcq part")

        self.empty = self.block(order_in_chapter=3)

    def listed(self, question_type):
        body = self.client.get(BLOCKS_URL, {"question_type": question_type}, **self.auth).json()
        return sorted(row["id"] for row in body["data"])

    def test_it_returns_only_blocks_that_are_wholly_that_type(self):
        self.assertEqual(self.listed("mcq"), [self.mcq.pk])
        self.assertEqual(self.listed("cq"), [self.cq.pk])

    def test_a_group_with_one_stray_part_belongs_to_neither(self):
        """`.filter(...).exclude(...)` across two to-many paths returned this
        block under *both* types -- measured, not assumed."""
        self.assertNotIn(self.mixed.pk, self.listed("mcq"))
        self.assertNotIn(self.mixed.pk, self.listed("cq"))

    def test_a_block_with_no_questions_belongs_to_neither(self):
        self.assertNotIn(self.empty.pk, self.listed("mcq"))
        self.assertNotIn(self.empty.pk, self.listed("cq"))

    def test_a_matching_group_is_listed_once_despite_its_parts(self):
        """Two CQ parts, one row: `Exists` does not fan the join out."""
        self.assertEqual(self.listed("cq").count(self.cq.pk), 1)


class PermissionTests(QuestionTestCase):
    """Teaching staff, since `apps.exam` lets teachers build papers out of this.

    The bank is shared as a result: any teacher may edit any other teacher's
    question. Exams are owned; questions are not.
    """

    def setUp(self):
        super().setUp()
        self.solo = self.block()
        self.question = Question.objects.create(block=self.solo, prompt_content="?")

    def _urls(self):
        return [
            BLOCKS_URL,
            QUESTIONS_URL,
            detail("question_block", self.solo.pk),
            detail("question", self.question.pk),
        ]

    def test_a_student_is_refused(self):
        student = User.objects.create_user(phone="01810002222", name="Student")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=student).key}"}
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_a_teacher_may_author_the_bank(self):
        """A teacher cannot assemble an exam out of questions they cannot see."""
        teacher = User.objects.create_user(phone="01810004444", name="Teacher", role=User.Role.TEACHER)
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=teacher).key}"}

        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 200, url)

        created = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "kind": "standalone"},
            content_type="application/json",
            **auth,
        )
        self.assertEqual(created.status_code, 201)

    def test_a_moderator_is_refused(self):
        """The notices desk has no business in the question bank."""
        moderator = User.objects.create_user(phone="01810005555", name="Moderator", role=User.Role.MODERATOR)
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=moderator).key}"}
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        """The project default is `IsAuthenticatedOrReadOnly`, so a view that
        forgets `permission_classes` would serve the answer key to anyone."""
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 401, url)


class RefreshQuestionCountTests(QuestionTestCase):
    """`question_count` on the curriculum is recounted on demand, not on write."""

    URL = reverse("api:question:admin_question_counts_refresh")

    def setUp(self):
        super().setUp()
        self.binary = Topic.objects.create(name="Binary", chapter=self.chapter)
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

    def test_the_refresh_counts_subjects_and_chapters_too(self):
        Chapter.objects.create(name="Networking", subject=self.ict, chapter_number=2)
        self.client.post(self.URL, **self.auth)
        self.hsc.refresh_from_db()
        self.ict.refresh_from_db()
        self.assertEqual((self.hsc.subject_count, self.ict.chapter_count), (1, 2))

    def test_the_command_does_the_same(self):
        call_command("refresh_question_counts", stdout=StringIO())
        self.assertEqual(self.counts(), [2, 2, 2, 2, 1])

    def test_teaching_staff_only(self):
        teacher = User.objects.create_user(phone="01700002222", name="Teacher", role=User.Role.TEACHER)
        student = User.objects.create_user(phone="01700003333", name="Student")
        for user, expected in ((teacher, 200), (student, 403)):
            auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=user).key}"}
            with self.subTest(user=user.name):
                self.assertEqual(self.client.post(self.URL, **auth).status_code, expected)


class NoTopicFilterTests(QuestionTestCase):
    """`?no_topic=true` lists a chapter's questions that carry no topic."""

    def test_only_untagged_blocks_are_listed_and_each_once(self):
        binary = Topic.objects.create(name="Binary", chapter=self.chapter)
        gates = Topic.objects.create(name="Gates", chapter=self.chapter)
        tagged = self.block()
        tagged.topics.add(binary, gates)
        untagged = self.block()

        body = self.client.get(BLOCKS_URL, {"chapter": self.chapter.pk, "no_topic": "true"}, **self.auth).json()
        self.assertEqual([row["id"] for row in body["data"]], [untagged.pk])

        body = self.client.get(BLOCKS_URL, {"chapter": self.chapter.pk, "no_topic": "false"}, **self.auth).json()
        self.assertEqual([row["id"] for row in body["data"]], [tagged.pk])


class BlockTopicTests(QuestionTestCase):
    """A block's topics are topics of its chapter."""

    def test_a_topic_from_another_chapter_is_refused(self):
        physics = Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science, slug="phy")
        optics = Topic.objects.create(name="Optics", chapter=Chapter.objects.create(name="Light", subject=physics))
        response = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "chapter_id": self.chapter.pk, "topic_ids": [optics.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("topic_ids", response.json()["errors"])

    def test_a_topic_of_its_own_chapter_is_accepted(self):
        binary = Topic.objects.create(name="Binary", chapter=self.chapter)
        response = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "chapter_id": self.chapter.pk, "topic_ids": [binary.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_moving_to_another_chapter_needs_its_topics_to_follow(self):
        block = self.block()
        block.topics.add(Topic.objects.create(name="Binary", chapter=self.chapter))
        other = Chapter.objects.create(name="Networking", subject=self.ict, chapter_number=2)
        response = self.client.patch(
            detail("question_block", block.pk), {"chapter_id": other.pk}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
