"""Slugs and uniqueness of the academic taxonomy."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academic.models import Batch, ClassLevel, Group, Subject
from apps.academic.tests.base import (
    SUBJECTS_URL,
    AcademicTestCase,
)


class SlugTests(AcademicTestCase):
    def test_a_bangla_name_still_gets_an_english_slug(self):
        level = ClassLevel.objects.create(name="আলিম")
        self.assertEqual(level.slug, "classlevel")

    def test_a_typed_bangla_slug_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            Group(name="বিজ্ঞান", slug="বিজ্ঞান").full_clean()
        self.assertIn("slug", caught.exception.message_dict)

    def test_a_subject_slug_carries_its_level_and_group(self):
        """A name-only slug would collide across levels and groups."""
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
