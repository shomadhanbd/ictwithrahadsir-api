from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.academic.models import Batch, ClassLevel
from apps.communication.models import Notice, NoticeCategory, NoticeSeen
from apps.core.testing import bearer, make_user
from apps.courses.models import Course, Enrollment
from apps.identity.models import User
from apps.profiles.models import StudentProfile

NOTICES_URL = reverse("api:communication:notice_list")
NOTICE_CATEGORY_URL = reverse("api:communication:notice_category_list")
UNREAD_URL = reverse("api:communication:my_unread_notices")
SEEN_URL = reverse("api:communication:my_notices_seen")


def titles(response):
    return sorted(notice["title"] for notice in response.json()["data"])


class NoticeBoardTests(APITestCase):
    def setUp(self):
        self.category = NoticeCategory.objects.create(title="Exam", slug="exam")
        self.notice = Notice.objects.create(title="Exam schedule")
        self.notice.categories.add(self.category)
        Notice.objects.create(title="Holiday")

    def test_notices_are_paginated(self):
        self.assertEqual(self.client.get(NOTICES_URL).json()["meta"]["total"], 2)

    def test_notices_filter_by_category(self):
        self.assertEqual(titles(self.client.get(NOTICES_URL, {"category_id": self.category.pk})), ["Exam schedule"])

    def test_a_category_that_is_not_an_id_is_a_422_not_a_500(self):
        response = self.client.get(NOTICES_URL, {"category_id": "abc"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("category_id", response.json()["errors"])

    def test_notice_categories_are_listed(self):
        body = self.client.get(NOTICE_CATEGORY_URL).json()
        self.assertEqual([c["title"] for c in body["data"]], ["Exam"])

    def test_admins_see_each_categorys_notice_count_and_filter_by_it(self):
        admin = bearer(make_user(role=User.Role.ADMIN))
        categories = self.client.get(reverse("api:communication:admin_notice_category_list"), **admin).json()["data"]
        self.assertEqual([(c["title"], c["notice_count"]) for c in categories], [("Exam", 1)])
        url = reverse("api:communication:admin_notice_list")
        self.assertEqual(titles(self.client.get(url, {"category": self.category.pk}, **admin)), ["Exam schedule"])

    def test_a_notice_body_is_stripped_of_script(self):
        admin = bearer(make_user(role=User.Role.ADMIN))
        body = {"title": "Notice", "body": '<p>খবর</p><a href="javascript:steal()">x</a>'}
        response = self.client.post(reverse("api:communication:admin_notice_list"), body, format="json", **admin)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn("javascript", Notice.objects.get(title="Notice").body)

    def test_admins_edit_and_delete_a_notice_by_its_id(self):
        admin = bearer(make_user(role=User.Role.ADMIN))
        url = reverse("api:communication:admin_notice_detail", args=[self.notice.pk])

        response = self.client.patch(url, {"title": "Exam schedule (updated)"}, format="json", **admin)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn("slug", response.json())
        self.assertEqual(Notice.objects.get(pk=self.notice.pk).title, "Exam schedule (updated)")

        self.assertEqual(self.client.delete(url, **admin).status_code, 204)
        self.assertFalse(Notice.objects.filter(pk=self.notice.pk).exists())


class AudienceTests(APITestCase):
    def setUp(self):
        self.hsc, _ = ClassLevel.objects.get_or_create(slug="hsc", defaults={"name": "HSC"})
        self.ssc, _ = ClassLevel.objects.get_or_create(slug="ssc", defaults={"name": "SSC"})
        self.batch = Batch.objects.create(name="HSC-2027", slug="hsc-2027-notices", class_level=self.hsc)
        self.course = Course.objects.create(
            title="ICT Live", slug="ict-live-notices", status="published", batch=self.batch
        )

        Notice.objects.create(title="For everyone")
        Notice.objects.create(title="For HSC").class_levels.add(self.hsc)
        Notice.objects.create(title="For the batch").batches.add(self.batch)

    def student(self, level=None):
        user = make_user()
        StudentProfile.objects.update_or_create(user=user, defaults={"class_level": level})
        return user

    def test_a_visitor_reads_only_notices_for_everyone(self):
        self.assertEqual(titles(self.client.get(NOTICES_URL)), ["For everyone"])

    def test_a_student_reads_their_class_levels_notices(self):
        hsc = self.client.get(NOTICES_URL, **bearer(self.student(self.hsc)))
        ssc = self.client.get(NOTICES_URL, **bearer(self.student(self.ssc)))
        self.assertEqual(titles(hsc), ["For HSC", "For everyone"])
        self.assertEqual(titles(ssc), ["For everyone"])

    def test_a_batch_notice_reaches_students_of_that_batchs_courses_while_enrolled(self):
        user = self.student()
        enrolment = Enrollment.objects.create(user=user, course=self.course)
        self.assertIn("For the batch", titles(self.client.get(NOTICES_URL, **bearer(user))))

        enrolment.valid_till = timezone.now() - timezone.timedelta(days=1)
        enrolment.save()
        self.assertNotIn("For the batch", titles(self.client.get(NOTICES_URL, **bearer(user))))

    def test_staff_read_every_notice(self):
        moderator = bearer(make_user(role=User.Role.MODERATOR))
        self.assertEqual(len(titles(self.client.get(NOTICES_URL, **moderator))), 3)

    def test_each_notice_names_its_audience(self):
        body = self.client.get(NOTICES_URL, **bearer(make_user(role=User.Role.ADMIN))).json()["data"]
        audience = {notice["title"]: notice["audience"] for notice in body}
        self.assertEqual(audience, {"For everyone": [], "For HSC": ["HSC"], "For the batch": ["HSC-2027"]})

    def test_admins_aim_a_notice_at_class_levels_and_batches(self):
        admin = bearer(make_user(role=User.Role.ADMIN))
        body = {"title": "Mock test", "class_level_ids": [self.ssc.pk], "batch_ids": [self.batch.pk]}
        response = self.client.post(reverse("api:communication:admin_notice_list"), body, format="json", **admin)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["audience"], ["SSC", "HSC-2027"])


class UnreadTests(APITestCase):
    def setUp(self):
        self.user = make_user()
        self.auth = bearer(self.user)
        Notice.objects.create(title="One")
        Notice.objects.create(title="Two")

    def test_new_notices_count_as_unread_until_the_board_is_opened(self):
        self.assertEqual(self.client.get(UNREAD_URL, **self.auth).json(), {"count": 2})
        self.assertEqual(self.client.post(SEEN_URL, **self.auth).status_code, 200)
        self.assertEqual(self.client.get(UNREAD_URL, **self.auth).json(), {"count": 0})

        Notice.objects.create(title="Three")
        self.assertEqual(self.client.get(UNREAD_URL, **self.auth).json(), {"count": 1})

    def test_a_first_visit_counts_only_the_last_month(self):
        Notice.objects.filter(title="One").update(created_at=timezone.now() - timezone.timedelta(days=60))
        self.assertEqual(self.client.get(UNREAD_URL, **self.auth).json(), {"count": 1})
        self.assertFalse(NoticeSeen.objects.exists())

    def test_a_notice_for_another_class_is_never_unread(self):
        level, _ = ClassLevel.objects.get_or_create(slug="ssc", defaults={"name": "SSC"})
        Notice.objects.create(title="SSC only").class_levels.add(level)
        self.assertEqual(self.client.get(UNREAD_URL, **self.auth).json(), {"count": 2})

    def test_a_visitor_has_no_unread_count(self):
        self.assertEqual(self.client.get(UNREAD_URL).status_code, 401)
