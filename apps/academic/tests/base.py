from django.test import TestCase
from django.urls import reverse

from apps.academic.models import ClassLevel, Group
from apps.core.testing import bearer, make_user
from apps.identity.models import User

SUBJECTS_URL = reverse("api:academic:admin_subject_list")
LEVELS_URL = reverse("api:academic:admin_class_level_list")
GROUPS_URL = reverse("api:academic:admin_group_list")
BATCHES_URL = reverse("api:academic:admin_batch_list")
CHAPTERS_URL = reverse("api:academic:admin_chapter_list")
TOPICS_URL = reverse("api:academic:admin_topic_list")


def detail(resource, pk):
    return reverse(f"api:academic:admin_{resource}_detail", args=[pk])


class AcademicTestCase(TestCase):
    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))

        self.ssc = ClassLevel.objects.create(name="এসএসসি", slug="ssc", order=0)
        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc", order=1)
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.arts = Group.objects.create(name="মানবিক", slug="arts")
