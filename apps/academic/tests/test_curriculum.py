"""Chapters, topics and the integrity of a used curriculum."""

from apps.academic.models import Chapter, Subject, Topic
from apps.academic.tests.base import (
    CHAPTERS_URL,
    TOPICS_URL,
    AcademicTestCase,
    detail,
)
from apps.core.testing import next_slug


class ChapterTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.other = Subject.objects.create(
            name="ICT", class_level=self.ssc, group=self.science, slug="ict-ssc-science"
        )

    def test_a_subject_with_chapters_cannot_be_deleted(self):
        Chapter.objects.create(slug=next_slug("chapter"), name="Number Systems", subject=self.ict)

        response = self.client.delete(detail("subject", self.ict.pk), **self.auth)

        self.assertEqual(response.status_code, 409)
        self.assertTrue(Subject.objects.filter(pk=self.ict.pk).exists())

    def test_it_can_be_retired_instead(self):
        Chapter.objects.create(slug=next_slug("chapter"), name="Number Systems", subject=self.ict)

        response = self.client.patch(
            detail("subject", self.ict.pk),
            {"is_active": False},
            content_type="application/json",
            **self.auth,
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_active"])

    def test_the_list_can_be_scoped_and_costs_one_query(self):
        Chapter.objects.create(
            slug=next_slug("chapter"), name="Number Systems", subject=self.ict, practice_enabled=True
        )
        Chapter.objects.create(slug=next_slug("chapter"), name="Digital Devices", subject=self.other)

        scoped = self.client.get(CHAPTERS_URL, {"subject": self.ict.pk}, **self.auth).json()
        practised = self.client.get(CHAPTERS_URL, {"practice_enabled": "true"}, **self.auth).json()

        self.assertEqual(scoped["meta"]["total"], 1)
        self.assertEqual(scoped["data"][0]["subject_name"], "ICT")
        self.assertEqual(practised["meta"]["total"], 1)
        # token, role groups, count, page
        with self.assertNumQueries(4):
            self.client.get(CHAPTERS_URL, **self.auth)

    def test_a_new_chapter_is_active_but_not_yet_practised(self):
        chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Number Systems", subject=self.ict)
        self.assertFalse(chapter.practice_enabled)
        self.assertTrue(chapter.is_active)


class TopicTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        subject = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(
            slug=next_slug("chapter"), name="Number Systems", subject=subject, chapter_number=1
        )

    def test_a_chapter_with_topics_cannot_be_deleted(self):
        Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)

        response = self.client.delete(detail("chapter", self.chapter.pk), **self.auth)

        self.assertEqual(response.status_code, 409)

    def test_a_chapter_with_no_topics_can_be_deleted(self):
        response = self.client.delete(detail("chapter", self.chapter.pk), **self.auth)
        self.assertEqual(response.status_code, 204)

    def test_the_list_can_be_scoped_to_one_chapter(self):
        Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)

        body = self.client.get(TOPICS_URL, {"chapter": self.chapter.pk}, **self.auth).json()

        self.assertEqual(body["meta"]["total"], 1)
        self.assertEqual(body["data"][0]["chapter_name"], "Number Systems")

    def test_topics_are_listed_in_their_order(self):
        for name, slug in (("হেক্সাডেসিমেল", "hexadecimal"), ("বাইনারি", "binary")):
            self.client.post(TOPICS_URL, {"name": name, "slug": slug, "chapter_id": self.chapter.pk}, **self.auth)
        names = [
            t["name"] for t in self.client.get(TOPICS_URL, {"chapter": self.chapter.pk}, **self.auth).json()["data"]
        ]
        self.assertEqual(names, ["হেক্সাডেসিমেল", "বাইনারি"])

        first = Topic.objects.get(name="বাইনারি")
        self.client.patch(detail("topic", first.pk), {"order": 0}, content_type="application/json", **self.auth)
        Topic.objects.filter(name="হেক্সাডেসিমেল").update(order=1)
        names = [
            t["name"] for t in self.client.get(TOPICS_URL, {"chapter": self.chapter.pk}, **self.auth).json()["data"]
        ]
        self.assertEqual(names, ["বাইনারি", "হেক্সাডেসিমেল"])


class CurriculumIntegrityTests(AcademicTestCase):
    """Used chapters and topics stay put; recounted columns are read-only."""

    def setUp(self):
        super().setUp()
        from apps.question.models import QuestionBlock

        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict")
        self.physics = Subject.objects.create(name="Physics", class_level=self.hsc, group=self.science, slug="phy")
        self.chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Numbers", subject=self.ict)
        self.topic = Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)
        self.block = QuestionBlock.objects.create(subject=self.ict, chapter=self.chapter)

    def patch(self, resource, pk, body):
        return self.client.patch(detail(resource, pk), body, content_type="application/json", **self.auth)

    def test_a_chapter_with_questions_keeps_its_subject(self):
        response = self.patch("chapter", self.chapter.pk, {"subject_id": self.physics.pk})
        self.assertEqual(response.status_code, 422)
        self.assertIn("subject_id", response.json()["errors"])

    def test_an_empty_chapter_may_move(self):
        empty = Chapter.objects.create(slug=next_slug("chapter"), name="Empty", subject=self.ict)
        self.assertEqual(self.patch("chapter", empty.pk, {"subject_id": self.physics.pk}).status_code, 200)

    def test_a_tagged_topic_keeps_its_chapter(self):
        self.block.topics.add(self.topic)
        other = Chapter.objects.create(slug=next_slug("chapter"), name="Other", subject=self.ict)
        response = self.patch("topic", self.topic.pk, {"chapter_id": other.pk})
        self.assertEqual(response.status_code, 422)
        self.assertIn("chapter_id", response.json()["errors"])

    def test_structure_counts_are_live_and_read_only(self):
        self.patch("class_level", self.hsc.pk, {"subject_count": 99})
        self.patch("subject", self.ict.pk, {"chapter_count": 99})
        level = self.client.get(detail("class_level", self.hsc.pk), **self.auth).json()
        subject = self.client.get(detail("subject", self.ict.pk), **self.auth).json()
        subjects = Subject.objects.filter(class_level=self.hsc)
        chapters = Chapter.objects.filter(subject__class_level=self.hsc)
        self.assertEqual((level["subject_count"], level["chapter_count"]), (subjects.count(), chapters.count()))
        self.assertEqual(subject["chapter_count"], 1)

        Chapter.objects.create(slug=next_slug("chapter"), name="Networking", subject=self.ict, chapter_number=2)
        subject = self.client.get(detail("subject", self.ict.pk), **self.auth).json()
        self.assertEqual(subject["chapter_count"], 2)

    def test_question_count_is_read_only(self):
        for resource, pk in (("class_level", self.hsc.pk), ("subject", self.ict.pk), ("chapter", self.chapter.pk)):
            with self.subTest(resource=resource):
                response = self.patch(resource, pk, {"question_count": 999})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["question_count"], 0)
