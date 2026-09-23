"""The academic taxonomy: slugs, uniqueness, and what the admin panel asks for."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic
from apps.identity.models import User

SUBJECTS_URL = reverse("api:academic:admin_subject_list")
LEVELS_URL = reverse("api:academic:admin_class_level_list")
GROUPS_URL = reverse("api:academic:admin_group_list")
BATCHES_URL = reverse("api:academic:admin_batch_list")
CHAPTERS_URL = reverse("api:academic:admin_chapter_list")
TOPICS_URL = reverse("api:academic:admin_topic_list")


def detail(resource, pk):
    """Reversed rather than concatenated onto the list URL, so a renamed route
    fails here instead of quietly still passing."""
    return reverse(f"api:academic:admin_{resource}_detail", args=[pk])


class AcademicTestCase(TestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone="01700001111", name="Admin", password="Str0ngPass!23", role=User.Role.ADMIN
        )
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=admin).key}"}

        self.ssc = ClassLevel.objects.create(name="এসএসসি", slug="ssc", order=0)
        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc", order=1)
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.arts = Group.objects.create(name="মানবিক", slug="arts")


class SlugTests(AcademicTestCase):
    def test_a_bangla_name_still_gets_an_ascii_slug(self):
        """Django's `slugify` drops non-ASCII, so a Bangla name would otherwise
        slug to nothing at all."""
        level = ClassLevel.objects.create(name="আলিম")
        self.assertTrue(level.slug)
        self.assertTrue(level.slug.isascii())

    def test_a_subject_slug_carries_its_level_and_group(self):
        """The name alone repeats on every level and group, so a name-only slug
        would fall back to physics-2, physics-3."""
        rows = [
            Subject.objects.create(name="Physics", class_level=level, group=self.science)
            for level in (self.ssc, self.hsc)
        ]
        self.assertEqual([s.slug for s in rows], ["physics-ssc-science", "physics-hsc-science"])

    def test_a_batch_slug_does_not_repeat_the_level(self):
        named = Batch.objects.create(name="SSC-2027", class_level=self.ssc)
        bare = Batch.objects.create(name="2027", class_level=self.hsc)

        self.assertEqual(named.slug, "ssc-2027")
        self.assertEqual(bare.slug, "2027-hsc")

    def test_a_multi_part_level_slug_is_not_appended_twice(self):
        level = ClassLevel.objects.create(name="ষষ্ঠ শ্রেণি", slug="class-6")
        batch = Batch.objects.create(name="Class 6-2027", class_level=level)
        self.assertEqual(batch.slug, "class-6-2027")

    def test_an_explicit_slug_is_left_alone(self):
        subject = Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science, slug="phy")
        self.assertEqual(subject.slug, "phy")


class UniquenessTests(AcademicTestCase):
    def test_a_subject_is_unique_per_level_and_group(self):
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)

    def test_the_same_subject_name_is_fine_elsewhere(self):
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)
        Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science)
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.arts)
        self.assertEqual(Subject.objects.filter(name="Physics").count(), 3)

    def test_a_batch_is_unique_per_level(self):
        Batch.objects.create(name="2027", class_level=self.ssc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Batch.objects.create(name="2027", class_level=self.ssc)

    def test_the_api_reports_a_duplicate_rather_than_failing(self):
        payload = {"name": "Physics", "class_level_id": self.ssc.pk, "group_id": self.science.pk}
        self.client.post(SUBJECTS_URL, payload, content_type="application/json", **self.auth)

        response = self.client.post(SUBJECTS_URL, payload, content_type="application/json", **self.auth)

        self.assertEqual(response.status_code, 422)


class DeletionTests(AcademicTestCase):
    """A level and a group are reference data. Removing one used to take every
    subject and batch under it with no warning."""

    def test_a_level_in_use_cannot_be_deleted(self):
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)

        response = self.client.delete(detail("class_level", self.ssc.pk), **self.auth)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(ClassLevel.objects.filter(pk=self.ssc.pk).exists())

    def test_a_level_nothing_points_at_can_be_deleted(self):
        response = self.client.delete(detail("class_level", self.hsc.pk), **self.auth)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ClassLevel.objects.filter(pk=self.hsc.pk).exists())

    def test_a_level_with_batches_cannot_be_deleted(self):
        Batch.objects.create(name="2027", class_level=self.ssc)
        self.assertEqual(self.client.delete(detail("class_level", self.ssc.pk), **self.auth).status_code, 409)


class ListTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        for level in (self.ssc, self.hsc):
            for group in (self.science, self.arts):
                Subject.objects.create(name="ICT", class_level=level, group=group)

    def _totals(self, url, query=None):
        body = self.client.get(url, query or {}, **self.auth).json()
        return body["meta"]["total"], body["data"]

    def test_subjects_can_be_scoped_to_one_level(self):
        """`?class_level=` used to be accepted and silently ignored, so the
        panel could not narrow the list at all."""
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
        """Otherwise the panel has to fetch two more lists and join by id."""
        _, rows = self._totals(SUBJECTS_URL, {"class_level": self.ssc.pk, "group": self.arts.pk})

        self.assertEqual(rows[0]["class_level_name"], self.ssc.name)
        self.assertEqual(rows[0]["group_name"], self.arts.name)

    def test_the_list_costs_one_query_per_page(self):
        """`class_level_name` and `group_name` cross a relation, so without
        `select_related` each row would fetch its own."""
        # token, role groups, count, page -- the page query joins both
        # relations rather than fetching one per row.
        with self.assertNumQueries(4):
            self.client.get(SUBJECTS_URL, **self.auth)

    def test_ordering_is_stable_when_name_and_order_tie(self):
        """`name` repeats across levels and groups, so `order` + `name` is not
        a unique key -- a tie used to leave the page boundary undefined."""
        seen = []
        for page in (1, 2):
            body = self.client.get(SUBJECTS_URL, {"page": page, "per_page": 2}, **self.auth).json()
            seen.extend(row["id"] for row in body["data"])

        self.assertEqual(len(seen), len(set(seen)), f"a subject appeared twice: {seen}")


class BatchTests(AcademicTestCase):
    def test_batches_can_be_scoped_to_active_ones(self):
        Batch.objects.create(name="2027", class_level=self.ssc)
        Batch.objects.create(name="2026", class_level=self.ssc, is_active=False)

        body = self.client.get(BATCHES_URL, {"is_active": "true"}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["name"], "2027")

    def test_the_taxonomy_is_admin_only(self):
        student = User.objects.create_user(phone="01810002222", name="Student")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=student).key}"}
        for url in (SUBJECTS_URL, LEVELS_URL, BATCHES_URL):
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)


class RetireTests(AcademicTestCase):
    """Subjects and batches PROTECT the level and group they belong to, so
    anything in use cannot be deleted. `is_active` is the way out."""

    def test_a_level_in_use_can_be_retired_instead(self):
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)
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
        subject = Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)
        self.assertTrue(subject.is_active)

    def test_each_resource_can_be_filtered_by_status(self):
        Group.objects.create(name="ব্যবসায় শিক্ষা", slug="commerce", is_active=False)
        Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science, is_active=False)
        Batch.objects.create(name="2026", class_level=self.ssc, is_active=False)
        Batch.objects.create(name="2027", class_level=self.ssc)

        for url, expected in [(GROUPS_URL, 2), (SUBJECTS_URL, 0), (BATCHES_URL, 1)]:
            body = self.client.get(url, {"is_active": "true"}, **self.auth).json()
            self.assertEqual(body["meta"]["total"], expected, url)

    def test_retiring_hides_nothing_by_default(self):
        """The flag is opt-in, the same way `Batch.is_active` already behaved --
        an admin still sees retired rows unless they filter them out."""
        self.ssc.is_active = False
        self.ssc.save()

        body = self.client.get(LEVELS_URL, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 2)


class DetailRouteTests(AcademicTestCase):
    """Every detail route, for every resource. Only class levels had any
    coverage, and only for DELETE."""

    def setUp(self):
        super().setUp()
        self.subject = Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science)
        self.batch = Batch.objects.create(name="SSC-2027", class_level=self.ssc)

    def test_every_resource_is_retrievable(self):
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("group", self.science.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            response = self.client.get(detail(resource, pk), **self.auth)
            self.assertEqual(response.status_code, 200, resource)
            self.assertEqual(response.json()["id"], pk)

    def test_every_resource_is_patchable(self):
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("group", self.science.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            response = self.client.patch(
                detail(resource, pk),
                {"is_active": False},
                content_type="application/json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 200, resource)
            self.assertFalse(response.json()["is_active"], resource)

    def test_a_subject_and_batch_can_be_deleted(self):
        """Nothing protects these two, unlike the level and group they sit on."""
        for resource, pk, model in [
            ("subject", self.subject.pk, Subject),
            ("batch", self.batch.pk, Batch),
        ]:
            response = self.client.delete(detail(resource, pk), **self.auth)
            self.assertEqual(response.status_code, 204, resource)
            self.assertFalse(model.objects.filter(pk=pk).exists(), resource)

    def test_a_detail_route_is_admin_only(self):
        """The role matrix only covers collection paths, so these are checked
        here or nowhere."""
        student = User.objects.create_user(phone="01810003333", name="Student")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=student).key}"}
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("group", self.science.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            self.assertEqual(self.client.get(detail(resource, pk), **auth).status_code, 403, resource)

    def test_a_detail_route_is_closed_to_anonymous_callers(self):
        """The project default is `IsAuthenticatedOrReadOnly`, so a view that
        forgets `permission_classes` is world-readable."""
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("group", self.science.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            self.assertEqual(self.client.get(detail(resource, pk)).status_code, 401, resource)


class UnicodeSlugTests(AcademicTestCase):
    """Slugs are typed by hand so they can hold real Bangla. They are never
    *generated* as unicode -- Django's slugify strips Bengali vowel marks."""

    def test_a_typed_bangla_slug_is_stored_verbatim(self):
        group = Group.objects.create(name="ব্যবসায় শিক্ষা", slug="ব্যবসায়-শিক্ষা")
        group.refresh_from_db()
        self.assertEqual(group.slug, "ব্যবসায়-শিক্ষা")

    def test_a_blank_slug_falls_back_to_ascii_not_the_mangled_form(self):
        from django.utils.text import slugify

        name = "কারিগরি"
        group = Group.objects.create(name=name)

        self.assertTrue(group.slug.isascii(), group.slug)
        # What auto-generating unicode would have produced instead: slugify
        # strips Bengali vowel marks, so the "readable" slug is misspelt.
        self.assertNotEqual(group.slug, slugify(name, allow_unicode=True))

    def test_the_form_accepts_bangla_and_still_rejects_junk(self):
        """`allow_unicode=True` alone is not enough: Django's validator is
        `^[-\\w]+\\Z` and `\\w` excludes the combining vowel marks every real
        Bangla word carries, so বিজ্ঞান was rejected while কম was not."""
        from django.forms import modelform_factory

        form_class = modelform_factory(Group, fields="__all__")

        def accepts(slug):
            form = form_class(
                data={
                    "name": f"Probe {slug}",
                    "slug": slug,
                    "subject_count": 0,
                    "question_count": 0,
                    "chapter_count": 0,
                    "is_active": True,
                    "order": 0,
                }
            )
            form.is_valid()
            return "slug" not in form.errors

        self.assertTrue(accepts("বিজ্ঞান"))
        self.assertTrue(accepts("আলিম-২০২৭"))
        self.assertTrue(accepts("ict-hsc-science"))
        self.assertFalse(accepts("has space"))
        self.assertFalse(accepts("bad/slash"))

    def test_a_typed_slug_survives_a_round_trip_through_the_api(self):
        level = ClassLevel.objects.create(name="আলিম", slug="আলিম")

        body = self.client.get(detail("class_level", level.pk), **self.auth).json()

        self.assertEqual(body["slug"], "আলিম")


class ChapterTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.other = Subject.objects.create(
            name="ICT", class_level=self.ssc, group=self.science, slug="ict-ssc-science"
        )

    def test_the_slug_is_built_from_the_subject(self):
        chapter = Chapter.objects.create(name="Number Systems", subject=self.ict, chapter_number=1)
        self.assertEqual(chapter.slug, "number-systems-ict-hsc-science")

    def test_the_same_name_under_two_subjects_gets_two_clean_slugs(self):
        first = Chapter.objects.create(name="Number Systems", subject=self.ict)
        second = Chapter.objects.create(name="Number Systems", subject=self.other)

        self.assertEqual(first.slug, "number-systems-ict-hsc-science")
        self.assertEqual(second.slug, "number-systems-ict-ssc-science")

    def test_a_duplicate_within_one_subject_is_accepted_and_suffixed(self):
        """Uniqueness is carried by the slug alone, as in the reference: a
        repeated name or number is suffixed, not rejected. Adding a
        UniqueConstraint later is therefore a deliberate change, not a fix."""
        first = Chapter.objects.create(name="Number Systems", subject=self.ict, chapter_number=1)
        second = Chapter.objects.create(name="Number Systems", subject=self.ict, chapter_number=1)

        self.assertEqual(second.slug, f"{first.slug}-2")
        self.assertEqual(self.ict.chapters.count(), 2)

    def test_a_subject_with_chapters_cannot_be_deleted(self):
        Chapter.objects.create(name="Number Systems", subject=self.ict)

        response = self.client.delete(detail("subject", self.ict.pk), **self.auth)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Subject.objects.filter(pk=self.ict.pk).exists())

    def test_it_can_be_retired_instead(self):
        Chapter.objects.create(name="Number Systems", subject=self.ict)

        response = self.client.patch(
            detail("subject", self.ict.pk),
            {"is_active": False},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    def test_the_list_can_be_scoped_and_costs_one_query(self):
        Chapter.objects.create(name="Number Systems", subject=self.ict, is_locked=True)
        Chapter.objects.create(name="Digital Devices", subject=self.other)

        scoped = self.client.get(CHAPTERS_URL, {"subject": self.ict.pk}, **self.auth).json()
        locked = self.client.get(CHAPTERS_URL, {"is_locked": "true"}, **self.auth).json()

        self.assertEqual(scoped["meta"]["total"], 1)
        self.assertEqual(scoped["data"][0]["subject_name"], "ICT")
        self.assertEqual(locked["meta"]["total"], 1)
        # token, role groups, count, page -- the page joins the subject.
        with self.assertNumQueries(4):
            self.client.get(CHAPTERS_URL, **self.auth)

    def test_a_new_chapter_is_unlocked_and_active(self):
        chapter = Chapter.objects.create(name="Number Systems", subject=self.ict)
        self.assertFalse(chapter.is_locked)
        self.assertTrue(chapter.is_active)


class TopicTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        subject = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(name="Number Systems", subject=subject, chapter_number=1)

    def test_the_slug_is_built_from_the_chapter(self):
        topic = Topic.objects.create(name="Binary", chapter=self.chapter)
        self.assertEqual(topic.slug, "binary-number-systems-ict-hsc-science")

    def test_a_chapter_with_topics_cannot_be_deleted(self):
        Topic.objects.create(name="Binary", chapter=self.chapter)

        response = self.client.delete(detail("chapter", self.chapter.pk), **self.auth)

        self.assertEqual(response.status_code, 409)

    def test_a_chapter_with_no_topics_can_be_deleted(self):
        response = self.client.delete(detail("chapter", self.chapter.pk), **self.auth)
        self.assertEqual(response.status_code, 204)

    def test_the_list_can_be_scoped_to_one_chapter(self):
        Topic.objects.create(name="Binary", chapter=self.chapter)

        body = self.client.get(TOPICS_URL, {"chapter": self.chapter.pk}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["chapter_name"], "Number Systems")


class NewDetailRouteTests(AcademicTestCase):
    """The role matrix only covers collection paths, so detail routes are
    checked here or nowhere."""

    def setUp(self):
        super().setUp()
        subject = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(name="Number Systems", subject=subject)
        self.topic = Topic.objects.create(name="Binary", chapter=self.chapter)

    def _rows(self):
        return [("chapter", self.chapter.pk), ("topic", self.topic.pk)]

    def test_both_answer_get_and_patch(self):
        for resource, pk in self._rows():
            self.assertEqual(self.client.get(detail(resource, pk), **self.auth).status_code, 200)
            response = self.client.patch(
                detail(resource, pk),
                {"is_active": False},
                content_type="application/json",
                **self.auth,
            )
            self.assertEqual(response.status_code, 200, resource)
            self.assertFalse(response.json()["is_active"], resource)

    def test_both_are_admin_only(self):
        student = User.objects.create_user(phone="01810003333", name="Student")
        auth = {"HTTP_AUTHORIZATION": f"Bearer {Token.objects.create(user=student).key}"}
        for resource, pk in self._rows():
            self.assertEqual(self.client.get(detail(resource, pk), **auth).status_code, 403, resource)

    def test_both_are_closed_to_anonymous_callers(self):
        """The project default is `IsAuthenticatedOrReadOnly`, so a view that
        forgets `permission_classes` is world-readable."""
        for resource, pk in self._rows():
            self.assertEqual(self.client.get(detail(resource, pk)).status_code, 401, resource)
