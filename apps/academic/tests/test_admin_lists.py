"""Admin lists, filters, deletion and retirement."""

from django.urls import reverse

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic
from apps.academic.tests.base import (
    BATCHES_URL,
    GROUPS_URL,
    LEVELS_URL,
    SUBJECTS_URL,
    AcademicTestCase,
    detail,
)
from apps.core.testing import bearer, make_user, next_slug
from apps.identity.models import User


class ListTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        for level in (self.ssc, self.hsc):
            for group in (self.science, self.arts):
                Subject.objects.create(slug=next_slug("subject"), name="ICT", class_level=level, group=group)

    def _totals(self, url, query=None):
        body = self.client.get(url, query or {}, **self.auth).json()
        return body["meta"]["total"], body["data"]

    def test_subjects_can_be_scoped_to_one_level(self):
        total, _ = self._totals(SUBJECTS_URL, {"class_level": self.ssc.pk})
        self.assertEqual(total, 2)

    def test_subjects_can_be_scoped_to_one_group(self):
        total, _ = self._totals(SUBJECTS_URL, {"group": self.arts.pk})
        self.assertEqual(total, 2)

    def test_search_reaches_the_slug(self):
        """The names are Bangla; an admin types the English slug."""
        total, _ = self._totals(LEVELS_URL, {"search": "hsc"})
        self.assertEqual(total, 1)

    def test_a_subject_names_its_level_and_group(self):
        _, rows = self._totals(SUBJECTS_URL, {"class_level": self.ssc.pk, "group": self.arts.pk})

        self.assertEqual(rows[0]["class_level_name"], self.ssc.name)
        self.assertEqual(rows[0]["group_name"], self.arts.name)

    def test_the_list_costs_one_query_per_page(self):
        # token, role groups, count, page
        with self.assertNumQueries(4):
            self.client.get(SUBJECTS_URL, **self.auth)

    def test_ordering_is_stable_when_name_and_order_tie(self):
        """`order` + `name` is not unique, so a tie-breaker keeps pages disjoint."""
        seen = []
        for page in (1, 2):
            body = self.client.get(SUBJECTS_URL, {"page": page, "per_page": 2}, **self.auth).json()
            seen.extend(row["id"] for row in body["data"])

        self.assertEqual(len(seen), len(set(seen)), f"a subject appeared twice: {seen}")


class BatchTests(AcademicTestCase):
    def test_batches_can_be_scoped_to_active_ones(self):
        Batch.objects.create(slug=next_slug("batch"), name="2027", class_level=self.ssc)
        Batch.objects.create(slug=next_slug("batch"), name="2026", class_level=self.ssc, is_active=False)

        body = self.client.get(BATCHES_URL, {"is_active": "true"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "2027")

    def test_the_taxonomy_is_admin_only(self):
        auth = bearer(make_user())
        for url in (SUBJECTS_URL, LEVELS_URL, BATCHES_URL):
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)


class DeletionTests(AcademicTestCase):
    """A level or group in use cannot be deleted."""

    def test_a_level_in_use_cannot_be_deleted(self):
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science)

        response = self.client.delete(detail("class_level", self.ssc.pk), **self.auth)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(ClassLevel.objects.filter(pk=self.ssc.pk).exists())

    def test_a_level_nothing_points_at_can_be_deleted(self):
        response = self.client.delete(detail("class_level", self.hsc.pk), **self.auth)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ClassLevel.objects.filter(pk=self.hsc.pk).exists())

    def test_a_level_with_batches_cannot_be_deleted(self):
        Batch.objects.create(slug=next_slug("batch"), name="2027", class_level=self.ssc)
        self.assertEqual(self.client.delete(detail("class_level", self.ssc.pk), **self.auth).status_code, 409)


class RetireTests(AcademicTestCase):
    """`is_active` retires a row that is still in use."""

    def test_a_level_in_use_can_be_retired_instead(self):
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science)
        self.assertEqual(self.client.delete(detail("class_level", self.ssc.pk), **self.auth).status_code, 409)

        response = self.client.patch(
            detail("class_level", self.ssc.pk),
            {"is_active": False},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.ssc.refresh_from_db()
        self.assertFalse(self.ssc.is_active)

    def test_everything_is_active_by_default(self):
        for row in (self.ssc, self.science):
            self.assertTrue(row.is_active)
        subject = Subject.objects.create(
            slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science
        )
        self.assertTrue(subject.is_active)

    def test_each_resource_can_be_filtered_by_status(self):
        Group.objects.create(name="ব্যবসায় শিক্ষা", slug="commerce", is_active=False)
        Subject.objects.create(
            slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science, is_active=False
        )
        Batch.objects.create(slug=next_slug("batch"), name="2026", class_level=self.ssc, is_active=False)
        Batch.objects.create(slug=next_slug("batch"), name="2027", class_level=self.ssc)

        for url, expected in [(GROUPS_URL, 2), (SUBJECTS_URL, 0), (BATCHES_URL, 1)]:
            body = self.client.get(url, {"is_active": "true"}, **self.auth).json()
            self.assertEqual(body["meta"]["total"], expected, url)

    def test_retiring_hides_nothing_by_default(self):
        """Retired rows still list unless filtered out."""
        self.ssc.is_active = False
        self.ssc.save()

        body = self.client.get(LEVELS_URL, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 2)


class TeacherCurriculumLimitsTests(AcademicTestCase):
    """Teachers build subjects and chapters; the class levels and where subjects sit are an admin's."""

    def setUp(self):
        super().setUp()
        self.teacher = bearer(make_user(role=User.Role.TEACHER))
        self.subject = Subject.objects.create(
            slug=next_slug("subject"), name="ICT", class_level=self.ssc, group=self.science
        )

    def test_a_teacher_reads_but_cannot_change_a_class_level(self):
        url = reverse("api:academic:admin_class_level_detail", args=[self.ssc.pk])
        self.assertEqual(self.client.get(url, **self.teacher).status_code, 200)
        response = self.client.patch(url, {"is_active": False}, content_type="application/json", **self.teacher)
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ClassLevel.objects.get(pk=self.ssc.pk).is_active)

    def test_a_teacher_cannot_move_a_subject_to_another_class_or_group(self):
        url = reverse("api:academic:admin_subject_detail", args=[self.subject.pk])
        for body in ({"class_level_id": self.hsc.pk}, {"group_id": self.arts.pk}):
            with self.subTest(body=body):
                response = self.client.patch(url, body, content_type="application/json", **self.teacher)
                self.assertEqual(response.status_code, 403)
        self.subject.refresh_from_db()
        self.assertEqual((self.subject.class_level_id, self.subject.group_id), (self.ssc.pk, self.science.pk))

    def test_a_teacher_still_renames_a_subject_and_an_admin_moves_it(self):
        url = reverse("api:academic:admin_subject_detail", args=[self.subject.pk])
        response = self.client.patch(url, {"name": "ICT 2"}, content_type="application/json", **self.teacher)
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(url, {"class_level_id": self.hsc.pk}, content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_teacher_cannot_switch_a_subject_off_or_move_chapters_and_topics(self):
        chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Number systems", subject=self.subject)
        other = Subject.objects.create(
            slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science
        )
        topic = Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=chapter)
        other_chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Logic", subject=self.subject)
        for url, body in (
            (reverse("api:academic:admin_subject_detail", args=[self.subject.pk]), {"is_active": False}),
            (reverse("api:academic:admin_chapter_detail", args=[chapter.pk]), {"subject_id": other.pk}),
            (reverse("api:academic:admin_topic_detail", args=[topic.pk]), {"chapter_id": other_chapter.pk}),
        ):
            with self.subTest(url=url):
                response = self.client.patch(url, body, content_type="application/json", **self.teacher)
                self.assertEqual(response.status_code, 403)
        chapter.refresh_from_db()
        topic.refresh_from_db()
        self.assertEqual((chapter.subject_id, topic.chapter_id), (self.subject.pk, chapter.pk))

    def test_a_teacher_still_renames_chapters_and_topics(self):
        chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Number systems", subject=self.subject)
        url = reverse("api:academic:admin_chapter_detail", args=[chapter.pk])
        response = self.client.patch(url, {"name": "Numbers"}, content_type="application/json", **self.teacher)
        self.assertEqual(response.status_code, 200)
