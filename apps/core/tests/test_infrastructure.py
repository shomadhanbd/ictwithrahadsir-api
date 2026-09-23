"""Behaviour of the shared DRF/model plumbing in `apps.core`.

Covers slug allocation and the pagination link window, both rewritten for
cost rather than behaviour.
"""

from django.test import TestCase

from rest_framework.test import APITestCase

from apps.content.models import Notice
from apps.core.slugs import unique_slug
from apps.courses.models import Course


class UniqueSlugTests(TestCase):
    """Slug allocation is now one query per save rather than one per
    collision; it still has to hand out the same slugs."""

    def test_first_use_of_a_title_gets_the_bare_slug(self):
        self.assertEqual(Course.objects.create(title="Physics First").slug, "physics-first")

    def test_repeat_titles_get_incrementing_suffixes(self):
        slugs = [Course.objects.create(title="Model Test").slug for _ in range(4)]
        self.assertEqual(slugs, ["model-test", "model-test-2", "model-test-3", "model-test-4"])

    def test_a_gap_in_the_sequence_is_reused(self):
        Course.objects.create(title="Chemistry")
        second = Course.objects.create(title="Chemistry")
        third = Course.objects.create(title="Chemistry")
        self.assertEqual(third.slug, "chemistry-3")

        second.delete()
        self.assertEqual(Course.objects.create(title="Chemistry").slug, "chemistry-2")

    def test_a_longer_slug_sharing_the_prefix_is_not_a_collision(self):
        """`startswith` over-selects on purpose; it must not over-suffix."""
        Course.objects.create(title="Mathematics")
        self.assertEqual(Course.objects.create(title="Math").slug, "math")

    def test_suffixes_run_past_ten(self):
        """String sorting would put "-10" before "-2"; the search is numeric."""
        for _ in range(11):
            Course.objects.create(title="Batch")
        self.assertEqual(Course.objects.create(title="Batch").slug, "batch-12")

    def test_resaving_a_row_does_not_suffix_against_itself(self):
        course = Course.objects.create(title="Biology")
        course.title = "Biology Revised"
        course.save()
        self.assertEqual(course.slug, "biology")

    def test_slugs_are_allocated_per_model_not_globally(self):
        Course.objects.create(title="Announcement")
        self.assertEqual(Notice.objects.create(title="Announcement").slug, "announcement")

    def test_a_title_with_no_english_falls_back_to_the_model_name(self):
        slugs = [Course.objects.create(title="রসায়ন").slug for _ in range(2)]
        self.assertEqual(slugs, ["course", "course-2"])

    def test_unique_slug_respects_an_explicit_field_name(self):
        course = Course(title="Explicit")
        self.assertEqual(unique_slug(course, "Explicit", slug_field="slug"), "explicit")


class PaginationLinkWindowTests(APITestCase):
    """`meta.links` is windowed rather than one entry per page."""

    @classmethod
    def setUpTestData(cls):
        for i in range(200):
            Course.objects.create(title=f"Course {i}", active=True)

    def labels(self, response):
        return [link["label"] for link in response.data["meta"]["links"]]

    def test_envelope_keys_are_unchanged(self):
        body = self.client.get("/api/public/courses/?per_page=5").data
        self.assertEqual(list(body.keys()), ["data", "links", "meta"])
        self.assertEqual(list(body["links"].keys()), ["first", "last", "prev", "next"])
        self.assertEqual(
            list(body["meta"].keys()),
            ["current_page", "from", "last_page", "path", "per_page", "to", "total", "links"],
        )

    def test_link_count_does_not_grow_with_the_table(self):
        """40 pages of courses, but a bounded number of link objects."""
        response = self.client.get("/api/public/courses/?per_page=5")
        self.assertEqual(response.data["meta"]["last_page"], 40)
        self.assertLess(len(response.data["meta"]["links"]), 20)

    def test_the_window_keeps_both_endpoints_and_the_current_page(self):
        labels = self.labels(self.client.get("/api/public/courses/?per_page=5&page=20"))
        self.assertEqual(labels[0], "&laquo; Previous")
        self.assertEqual(labels[-1], "Next &raquo;")
        # First and last page stay reachable from deep in the table.
        self.assertIn("1", labels)
        self.assertIn("40", labels)
        self.assertIn("...", labels)
        for page in range(15, 26):
            self.assertIn(str(page), labels)

    def test_the_current_page_is_the_only_active_one(self):
        response = self.client.get("/api/public/courses/?per_page=5&page=20")
        active = [link["label"] for link in response.data["meta"]["links"] if link["active"]]
        self.assertEqual(active, ["20"])

    def test_a_short_table_is_not_elided(self):
        labels = self.labels(self.client.get("/api/public/courses/?per_page=100"))
        self.assertEqual(labels, ["&laquo; Previous", "1", "2", "Next &raquo;"])

    def test_page_links_carry_usable_urls(self):
        response = self.client.get("/api/public/courses/?per_page=5&page=20")
        for link in response.data["meta"]["links"]:
            if link["label"] == "...":
                self.assertIsNone(link["url"])
            elif link["label"].isdigit():
                self.assertIn(f"page={link['label']}", link["url"])
