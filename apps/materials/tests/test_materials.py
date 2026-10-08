from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel
from apps.core.testing import bearer, make_user
from apps.courses.models import Course, Enrollment
from apps.identity.models import User
from apps.materials.models import MaterialCategory, MaterialItem, MaterialTopic

VIDEO = "https://www.youtube.com/watch?v=K3R-NRESyzU"
PDF = "https://example.com/suggestion.pdf"


class MaterialsTestCase(APITestCase):
    def setUp(self):
        self.admin = bearer(make_user(role=User.Role.ADMIN))
        self.category = MaterialCategory.objects.create(name="মোটিভেশন")
        self.course = Course.objects.create(title="Physics", slug="physics-materials", status="published")

    def topic(self, **fields):
        fields.setdefault("is_published", True)
        topic = MaterialTopic.objects.create(category=self.category, title=fields.pop("title", "Topic"), **fields)
        MaterialItem.objects.create(topic=topic, kind="video", title="Video", url=VIDEO)
        MaterialItem.objects.create(topic=topic, kind="pdf", title="Sheet", url=PDF, order=1)
        return topic

    def students_only(self):
        topic = self.topic(title="Suggestion", access=MaterialTopic.Access.ENROLLED)
        topic.courses.set([self.course])
        return topic

    def library(self, auth=None, **params):
        return self.client.get(reverse("api:materials:library"), params, **(auth or {})).json()["data"]

    def detail(self, topic, auth=None):
        return next(row for row in self.library(auth) if row["id"] == topic.pk)


class AdminTests(MaterialsTestCase):
    def test_staff_build_a_topic_with_items(self):
        topic = self.client.post(
            reverse("api:materials:admin_topic_list"),
            {"category_id": self.category.pk, "title": "পরীক্ষার আগে কী করবেন", "is_published": True},
            format="json",
            **self.admin,
        )
        self.assertEqual(topic.status_code, 201, topic.content)
        topic_id = topic.json()["id"]
        items = (
            {"kind": "video", "url": VIDEO},
            {"kind": "pdf", "url": PDF},
            {"kind": "link", "url": "https://example.com"},
            {"kind": "book", "price": 350, "preview_url": PDF},
        )
        for fields in items:
            item = self.client.post(
                reverse("api:materials:admin_item_create"),
                {"topic_id": topic_id, "title": fields["kind"], **fields},
                format="json",
                **self.admin,
            )
            self.assertEqual(item.status_code, 201, item.content)
        body = self.client.get(reverse("api:materials:admin_topic_detail", args=[topic_id]), **self.admin).json()
        self.assertEqual([item["kind"] for item in body["items"]], ["video", "pdf", "link", "book"])
        self.assertEqual(body["counts"], {"pdf": 1, "video": 1, "link": 1, "book": 1})

    def test_a_video_must_be_on_youtube(self):
        topic = self.topic()
        response = self.client.post(
            reverse("api:materials:admin_item_create"),
            {"topic_id": topic.pk, "kind": "video", "title": "Clip", "url": "https://vimeo.com/1"},
            format="json",
            **self.admin,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("YouTube", str(response.json()["errors"]))

    def test_a_students_only_topic_names_its_courses(self):
        url = reverse("api:materials:admin_topic_list")
        body = {"category_id": self.category.pk, "title": "Suggestion", "access": "enrolled"}
        response = self.client.post(url, body, format="json", **self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("course_ids", response.json()["errors"])
        ok = self.client.post(url, {**body, "course_ids": [self.course.pk]}, format="json", **self.admin)
        self.assertEqual(ok.status_code, 201, ok.content)

    def test_items_move_up_and_down(self):
        topic = self.topic()
        sheet = topic.items.get(kind="pdf")
        response = self.client.post(
            reverse("api:materials:admin_item_move", args=[sheet.pk]), {"direction": "up"}, format="json", **self.admin
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(list(topic.items.values_list("kind", flat=True)), ["pdf", "video"])

    def test_a_book_needs_a_price(self):
        topic = self.topic()
        response = self.client.post(
            reverse("api:materials:admin_item_create"),
            {"topic_id": topic.pk, "kind": "book", "title": "Guide"},
            format="json",
            **self.admin,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("price", response.json()["errors"])

    def test_a_category_in_use_cannot_be_deleted(self):
        self.topic()
        response = self.client.delete(
            reverse("api:materials:admin_category_detail", args=[self.category.pk]), **self.admin
        )
        self.assertEqual(response.status_code, 409)

    def test_topics_filter_by_category(self):
        shown = self.topic()
        other = MaterialCategory.objects.create(name="সাজেশন")
        MaterialTopic.objects.create(category=other, title="Other")
        url = reverse("api:materials:admin_topic_list")
        rows = self.client.get(url, {"category": self.category.pk}, **self.admin).json()["data"]
        self.assertEqual([row["id"] for row in rows], [shown.pk])

    def test_moderators_manage_it_and_students_do_not(self):
        url = reverse("api:materials:admin_topic_list")
        self.assertEqual(self.client.get(url, **bearer(make_user(role=User.Role.MODERATOR))).status_code, 200)
        self.assertEqual(self.client.get(url, **bearer(make_user())).status_code, 403)


class PublicTests(MaterialsTestCase):
    def test_the_library_lists_published_topics_in_active_categories_with_their_items(self):
        self.topic(title="Shown")
        self.topic(title="Draft", is_published=False)
        hidden_category = MaterialCategory.objects.create(name="Hidden", is_active=False)
        MaterialTopic.objects.create(category=hidden_category, title="Retired", is_published=True)

        rows = self.library()
        self.assertEqual([row["title"] for row in rows], ["Shown"])
        self.assertEqual([item["kind"] for item in rows[0]["items"]], ["video", "pdf"])
        self.assertEqual(rows[0]["category"], {"id": self.category.pk, "name": "মোটিভেশন", "icon": ""})

    def test_a_free_topic_opens_for_everyone(self):
        body = self.detail(self.topic())
        self.assertFalse(body["locked"])
        self.assertEqual(body["items"][0]["url"], VIDEO)

    def test_a_students_only_topic_hides_its_links_from_others(self):
        topic = self.students_only()
        for auth in (None, bearer(make_user())):
            body = self.detail(topic, auth)
            self.assertTrue(body["locked"])
            self.assertEqual([item["url"] for item in body["items"]], [None, None])
            self.assertEqual(body["unlock_courses"], [{"slug": "physics-materials", "title": "Physics"}])

    def test_an_enrolled_student_opens_it_until_access_ends(self):
        topic = self.students_only()
        student = make_user()
        enrolment = Enrollment.objects.create(course=self.course, user=student)
        self.assertFalse(self.detail(topic, bearer(student))["locked"])

        Enrollment.objects.filter(pk=enrolment.pk).update(valid_till=timezone.now() - timezone.timedelta(days=1))
        self.assertTrue(self.detail(topic, bearer(student))["locked"])

    def test_staff_open_every_topic(self):
        self.assertFalse(self.detail(self.students_only(), self.admin)["locked"])

    def test_a_class_filter_keeps_topics_for_every_class(self):
        hsc = ClassLevel.objects.create(name="HSC", slug="hsc")
        ssc = ClassLevel.objects.create(name="SSC", slug="ssc")
        for_hsc = self.topic(title="HSC", class_level=hsc)
        self.topic(title="SSC", class_level=ssc)
        for_all = self.topic(title="All")
        rows = self.library(class_level="hsc")
        self.assertEqual({row["id"] for row in rows}, {for_hsc.pk, for_all.pk})
        hsc_row = next(row for row in rows if row["id"] == for_hsc.pk)
        self.assertEqual(hsc_row["class_level"], {"name": "HSC", "slug": "hsc"})


class EBookMigrationTests(TransactionTestCase):
    """E-books from before study material arrive as book items."""

    before = [("materials", "0001_initial")]
    after = [("materials", "0002_move_ebooks")]

    def test_each_ebook_becomes_a_book_item(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        # The retired `content` app's table, as an old database still has it.
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE TABLE content_ebook (id integer PRIMARY KEY, title varchar(255), description text, "
                "booking_link varchar(200), preview varchar(200), image varchar(200))"
            )
            cursor.execute(
                "INSERT INTO content_ebook VALUES (1, 'ICT Guide', '', 'https://shop.example/ict', "
                "'https://example.com/ict.pdf', NULL)"
            )

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.after)
        new = executor.loader.project_state(self.after).apps
        item = new.get_model("materials", "MaterialItem").objects.get()
        self.assertEqual((item.kind, item.title, item.url), ("book", "ICT Guide", "https://shop.example/ict"))
        self.assertEqual(item.preview_url, "https://example.com/ict.pdf")
        self.assertEqual(item.topic.category.name, "বই")

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())
