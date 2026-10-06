"""Question provenance: the exams a question appeared in."""

from django.db import IntegrityError, transaction

from apps.question.models import QuestionSource
from apps.question.tests.base import BLOCKS_URL, SOURCES_URL, QuestionTestCase, detail


class ProvenanceTests(QuestionTestCase):
    """A question appears in many exams, so provenance is rows, not three columns."""

    def setUp(self):
        super().setUp()
        self.dhaka_2019 = QuestionSource.objects.create(name="ঢাকা বোর্ড", year=2019)
        self.rajshahi_2021 = QuestionSource.objects.create(name="রাজশাহী বোর্ড", year=2021)

    def test_one_block_can_carry_several_exams(self):
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
        """Every provenance filter must match the same source row."""
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
        """Undated rows are kept unique by a partial constraint."""
        QuestionSource.objects.create(name="নটর ডেম কলেজ", kind=QuestionSource.Kind.COLLEGE)

        response = self.client.post(
            SOURCES_URL,
            {"kind": "college", "name": "নটর ডেম কলেজ"},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)

    def test_the_database_refuses_a_duplicate_exam(self):
        """The database constraint itself, not only the serializer."""
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
        unit = QuestionSource.objects.create(
            name="ঢাকা বিশ্ববিদ্যালয়", kind=QuestionSource.Kind.UNIVERSITY, unit="ka", year=2021
        )

        self.assertNotEqual(unit.slug, self.dhaka_2019.slug)
        self.assertTrue(unit.slug)
        self.assertIn("2021", unit.slug)

    def test_the_label_reads_as_one_exam(self):
        source = QuestionSource.objects.create(name="DU", kind=QuestionSource.Kind.UNIVERSITY, unit="ka", year=2021)

        self.assertEqual(source.label, "DU ka unit 2021")
