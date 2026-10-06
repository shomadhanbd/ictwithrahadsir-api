"""Slugs and uniqueness of the academic taxonomy."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.academic.models import Batch, Group, Subject
from apps.academic.tests.base import (
    SUBJECTS_URL,
    AcademicTestCase,
)
from apps.core.testing import next_slug


class SlugTests(AcademicTestCase):
    """Slugs are typed by staff: required, unique and English."""

    def test_the_api_requires_a_slug(self):
        response = self.client.post(
            SUBJECTS_URL, self.subject_payload(slug=""), content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("slug", response.json()["errors"])

    def test_a_taken_slug_is_refused(self):
        Subject.objects.create(slug="physics-ssc", name="Physics", class_level=self.ssc, group=self.arts)
        response = self.client.post(
            SUBJECTS_URL, self.subject_payload(slug="physics-ssc"), content_type="application/json", **self.auth
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("slug", response.json()["errors"])

    def test_a_typed_bangla_slug_is_rejected(self):
        with self.assertRaises(ValidationError) as caught:
            Group(name="বিজ্ঞান", slug="বিজ্ঞান").full_clean()
        self.assertIn("slug", caught.exception.message_dict)

    def test_the_typed_slug_is_kept_when_the_name_changes(self):
        subject = Subject.objects.create(name="Physics", class_level=self.ssc, group=self.science, slug="phy")
        subject.name = "Physics 1st Paper"
        subject.save()
        subject.refresh_from_db()
        self.assertEqual(subject.slug, "phy")

    def subject_payload(self, **overrides):
        return {"name": "Physics", "class_level_id": self.ssc.pk, "group_id": self.science.pk, **overrides}


class UniquenessTests(AcademicTestCase):
    def test_a_subject_is_unique_per_level_and_group(self):
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science)

    def test_the_same_subject_name_is_fine_elsewhere(self):
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science)
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.hsc, group=self.science)
        Subject.objects.create(slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.arts)
        self.assertEqual(Subject.objects.filter(name="Physics").count(), 3)

    def test_a_batch_is_unique_per_level(self):
        Batch.objects.create(slug=next_slug("batch"), name="2027", class_level=self.ssc)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Batch.objects.create(slug=next_slug("batch"), name="2027", class_level=self.ssc)

    def test_the_api_reports_a_duplicate_rather_than_failing(self):
        payload = {
            "name": "Physics",
            "slug": "physics-ssc-science",
            "class_level_id": self.ssc.pk,
            "group_id": self.science.pk,
        }
        self.client.post(SUBJECTS_URL, payload, content_type="application/json", **self.auth)

        response = self.client.post(SUBJECTS_URL, payload, content_type="application/json", **self.auth)

        self.assertEqual(response.status_code, 422)
