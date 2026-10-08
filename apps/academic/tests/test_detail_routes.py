"""Detail routes for every resource, and who may reach them."""

from apps.academic.models import Batch, Chapter, Subject, Topic
from apps.academic.tests.base import (
    AcademicTestCase,
    detail,
)
from apps.core.testing import bearer, make_user, next_slug


class DetailRouteTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        self.subject = Subject.objects.create(
            slug=next_slug("subject"), name="Physics", class_level=self.ssc, group=self.science
        )
        self.batch = Batch.objects.create(slug=next_slug("batch"), name="SSC-2027", class_level=self.ssc)

    def test_every_resource_is_retrievable(self):
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            response = self.client.get(detail(resource, pk), **self.auth)
            self.assertEqual(response.status_code, 200, resource)
            self.assertEqual(response.json()["id"], pk)

    def test_every_resource_is_patchable(self):
        for resource, pk in [
            ("class_level", self.ssc.pk),
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
        auth = bearer(make_user())
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            self.assertEqual(self.client.get(detail(resource, pk), **auth).status_code, 403, resource)

    def test_a_detail_route_is_closed_to_anonymous_callers(self):
        for resource, pk in [
            ("class_level", self.ssc.pk),
            ("subject", self.subject.pk),
            ("batch", self.batch.pk),
        ]:
            self.assertEqual(self.client.get(detail(resource, pk)).status_code, 401, resource)


class ChapterTopicDetailRouteTests(AcademicTestCase):
    def setUp(self):
        super().setUp()
        subject = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(slug=next_slug("chapter"), name="Number Systems", subject=subject)
        self.topic = Topic.objects.create(slug=next_slug("topic"), name="Binary", chapter=self.chapter)

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
        auth = bearer(make_user())
        for resource, pk in self._rows():
            self.assertEqual(self.client.get(detail(resource, pk), **auth).status_code, 403, resource)

    def test_both_are_closed_to_anonymous_callers(self):
        for resource, pk in self._rows():
            self.assertEqual(self.client.get(detail(resource, pk)).status_code, 401, resource)
