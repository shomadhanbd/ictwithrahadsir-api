"""Authoring questions, options and blocks through the admin API."""

from django.core.exceptions import ValidationError

from apps.academic.models import Chapter, Subject, Topic
from apps.core.testing import next_slug
from apps.question.api.private.serializers import AdminQuestionSerializer
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet
from apps.question.tests.base import BLOCKS_URL, QuestionTestCase, detail, saved_question


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
        return self.save_question(payload)

    def test_a_valid_mcq_is_accepted(self):
        response = self._post_question()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(saved_question(response)["options"]), 2)

    def test_an_mcq_needs_a_correct_option(self):
        """An empty answer would otherwise match an empty answer key."""
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

        self.assertEqual(response.status_code, 200)

    def test_a_cq_needs_no_options(self):
        response = self._post_question(question_type="cq", options=[])
        self.assertEqual(response.status_code, 200)

    def test_a_question_needs_exactly_one_owner(self):
        """The save endpoint always sets the owner from the block; the serializer still refuses none."""
        for payload in ({}, {"question_set_id": None}):
            form = AdminQuestionSerializer(data={"question_type": "cq", "prompt_content": "?", **payload})
            self.assertFalse(form.is_valid())

    def test_a_chapter_from_another_subject_is_refused(self):
        other = Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science, slug="phy-hsc-science")
        elsewhere = Chapter.objects.create(slug=next_slug("chapter"), name="Motion", subject=other)

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

    def test_an_mcq_needs_two_options_with_text(self):
        for options in (
            [{"content": "4", "is_correct": True, "position": 0}],
            [
                {"content": "4", "is_correct": True, "position": 0},
                {"content": "  ", "is_correct": False, "position": 1},
            ],
        ):
            with self.subTest(options=options):
                response = self._post_question(options=options)
                self.assertEqual(response.status_code, 422)
                self.assertIn("options", response.json()["errors"])

    def test_explanation_and_model_answer_are_saved(self):
        response = self._post_question(explanation="৪ = ১০০ (বাইনারি)", model_answer="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_question(response)["explanation"], "৪ = ১০০ (বাইনারি)")

    def test_question_text_is_plain_text_kept_verbatim(self):
        """Maths must survive: the frontends render this as text, so it is never HTML-escaped."""
        response = self._post_question(
            prompt_content="If x < 5 & y > 2, which holds?",
            options=[
                {"content": "x + y < 7", "is_correct": True, "position": 0},
                {"content": "x > y", "is_correct": False, "position": 1},
            ],
        )

        self.assertEqual(response.status_code, 200, response.content)
        body = saved_question(response)
        self.assertEqual(body["prompt_content"], "If x < 5 & y > 2, which holds?")
        self.assertEqual(body["options"][0]["content"], "x + y < 7")


class PartialUpdateTests(QuestionTestCase):
    """An edit is validated against what the question will end up with."""

    def setUp(self):
        super().setUp()
        self.question = Question.objects.create(block=self.block(), prompt_content="2 + 2 = ?")
        QuestionOption.objects.create(question=self.question, content="4", is_correct=True, position=0)
        QuestionOption.objects.create(question=self.question, content="5", is_correct=False, position=1)

    def patch(self, payload):
        return self.save_question(payload, question=self.question)

    def test_editing_only_the_prompt_keeps_the_existing_answer_key(self):
        response = self.patch({"prompt_content": "2 + 2 = কত?"})

        self.assertEqual(response.status_code, 200)
        self.question.refresh_from_db()
        self.assertEqual(self.question.prompt_content, "2 + 2 = কত?")

    def test_an_edit_that_would_break_the_answer_key_is_still_refused(self):
        response = self.patch({"options": [{"content": "4", "is_correct": False, "position": 0}]})

        self.assertEqual(response.status_code, 422)

    def test_switching_to_multiple_is_checked_against_the_stored_options(self):
        """With no options in the request, the stored ones are judged."""
        self.question.options.update(is_correct=True)

        response = self.patch({"metadata": {"select_mode": "single"}})

        self.assertEqual(response.status_code, 422)


class OptionIdentityTests(QuestionTestCase):
    """Options keep their ids across an edit, since answers point at them."""

    def setUp(self):
        super().setUp()
        self.question = Question.objects.create(block=self.block(), prompt_content="?")
        self.first = QuestionOption.objects.create(question=self.question, content="4", is_correct=True, position=0)
        self.second = QuestionOption.objects.create(question=self.question, content="5", is_correct=False, position=1)

    def patch(self, options):
        return self.save_question({"options": options}, question=self.question)

    def test_an_edited_option_keeps_its_id(self):
        response = self.patch(
            [
                {"id": self.first.pk, "content": "চার", "is_correct": True, "position": 0},
                {"id": self.second.pk, "content": "5", "is_correct": False, "position": 1},
            ]
        )

        self.assertEqual(response.status_code, 200)
        options = saved_question(response, self.question.pk)["options"]
        self.assertEqual([o["id"] for o in options], [self.first.pk, self.second.pk])
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
        """`(question, position)` is unique, so a swap parks the rows first."""
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
        with self.assertRaises(ValidationError):
            QuestionSet(block=self.block(), stimulus_content="উদ্দীপক").clean()

    def test_a_stimulus_set_is_accepted_on_a_group_block(self):
        QuestionSet(block=self.block(kind=QuestionBlock.Kind.GROUP), stimulus_content="উদ্দীপক").clean()

    def test_a_question_cannot_hang_directly_off_a_group_block(self):
        group = self.block(kind=QuestionBlock.Kind.GROUP)
        form = AdminQuestionSerializer(data={"block_id": group.pk, "question_type": "cq", "prompt_content": "?"})

        self.assertFalse(form.is_valid())
        self.assertIn("block_id", form.errors)

    def test_a_question_cannot_join_a_set_hanging_off_a_standalone_block(self):
        # Only the ORM can build this contradiction.
        question_set = QuestionSet.objects.create(block=self.block(), stimulus_content="উদ্দীপক")

        form = AdminQuestionSerializer(
            data={"question_set_id": question_set.pk, "question_type": "cq", "prompt_content": "?"}
        )

        self.assertFalse(form.is_valid())
        self.assertIn("question_set_id", form.errors)

    def test_the_admin_form_path_refuses_it_too(self):
        with self.assertRaises(ValidationError):
            Question(block=self.block(kind=QuestionBlock.Kind.GROUP), prompt_content="?").clean()


class StimulusAuthoringTests(QuestionTestCase):
    """Creative questions are authored through the block that owns them."""

    def create(self, **overrides):
        payload = {"subject_id": self.ict.pk, "kind": "group", **overrides}
        return self.client.post(BLOCKS_URL, payload, content_type="application/json", **self.auth)

    def test_a_group_block_is_created_with_its_stimulus(self):
        response = self.create(question_set={"stimulus_content": "উদ্দীপক", "stimulus_type": "text"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["question_set"]["stimulus_content"], "উদ্দীপক")

    def test_its_parts_can_then_be_attached(self):
        block = self.create(question_set={"stimulus_content": "উদ্দীপক"}).json()

        part = self.save_question(
            {
                "question_set_id": block["question_set"]["id"],
                "question_type": "cq",
                "label": "ক",
                "prompt_content": "part ক",
            }
        )

        self.assertEqual(part.status_code, 200)
        self.assertEqual(saved_question(part)["label"], "ক")

    def test_editing_the_stimulus_keeps_its_parts(self):
        """The stimulus is edited in place, so its parts survive."""
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
        response = self.create(kind="standalone", question_set={"stimulus_content": "nope"})

        self.assertEqual(response.status_code, 422)
        self.assertIn("kind", response.json()["errors"])


class BlockTopicTests(QuestionTestCase):
    """A block's topics are topics of its chapter."""

    def test_a_topic_from_another_chapter_is_refused(self):
        physics = Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science, slug="phy")
        optics = Topic.objects.create(
            slug=next_slug("topic"),
            name="Optics",
            chapter=Chapter.objects.create(slug=next_slug("chapter"), name="Light", subject=physics),
        )
        response = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "chapter_id": self.chapter.pk, "topic_ids": [optics.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("topic_ids", response.json()["errors"])

    def test_a_topic_of_its_own_chapter_is_accepted(self):
        binary = Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)
        response = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "chapter_id": self.chapter.pk, "topic_ids": [binary.pk]},
            content_type="application/json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_moving_to_another_chapter_needs_its_topics_to_follow(self):
        block = self.block()
        block.topics.add(Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter))
        other = Chapter.objects.create(slug=next_slug("chapter"), name="Networking", subject=self.ict, chapter_number=2)
        response = self.client.patch(
            detail("question_block", block.pk), {"chapter_id": other.pk}, content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)


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
        return self.save_question(payload)

    def test_a_types_settings_are_stored_normalised(self):
        """An omitted setting gets its declared default."""
        body = saved_question(self.post())

        self.assertEqual(body["metadata"], {"select_mode": "single"})

    def test_a_setting_the_type_does_not_have_is_refused(self):
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(saved_question(response)["metadata"], {})

    def test_the_model_and_the_registry_cannot_drift(self):
        from apps.question import kinds

        self.assertEqual(sorted(kinds.REGISTRY), sorted(Question.Type.values))
