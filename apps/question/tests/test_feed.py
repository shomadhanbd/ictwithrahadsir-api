"""The block feed: its tree, search and filters."""

from apps.academic.models import Topic
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet
from apps.question.tests.base import BLOCKS_URL, QuestionTestCase


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
        body = self.client.get(BLOCKS_URL, {"search": "part 1"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["id"], self.group_block.pk)

    def test_a_block_matching_twice_is_listed_once(self):
        """A search across a to-many join must not repeat a block."""
        body = self.client.get(BLOCKS_URL, {"search": "part"}, **self.auth).json()

        ids = [block["id"] for block in body["data"]]
        self.assertEqual(ids, [self.group_block.pk])
        self.assertEqual(body["meta"]["total"], 1)

    def test_the_list_can_be_scoped(self):
        body = self.client.get(BLOCKS_URL, {"kind": "group"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["id"], self.group_block.pk)


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
        self.assertNotIn(self.mixed.pk, self.listed("mcq"))
        self.assertNotIn(self.mixed.pk, self.listed("cq"))

    def test_a_block_with_no_questions_belongs_to_neither(self):
        self.assertNotIn(self.empty.pk, self.listed("mcq"))
        self.assertNotIn(self.empty.pk, self.listed("cq"))

    def test_a_matching_group_is_listed_once_despite_its_parts(self):
        """Two CQ parts, one row: `Exists` does not fan the join out."""
        self.assertEqual(self.listed("cq").count(self.cq.pk), 1)


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
