from django.test import TestCase
from django.urls import reverse

from apps.academic.models import Chapter, ClassLevel, Group, Subject
from apps.core.testing import bearer, make_user, next_slug
from apps.identity.models import User
from apps.question.models import QuestionBlock

BLOCKS_URL = reverse("api:question:admin_question_block_list")
QUESTIONS_URL = reverse("api:question:admin_question_list")
SOURCES_URL = reverse("api:question:admin_question_source_list")


def detail(resource, pk):
    return reverse(f"api:question:admin_{resource}_detail", args=[pk])


class QuestionTestCase(TestCase):
    def setUp(self):
        self.auth = bearer(make_user(role=User.Role.ADMIN))

        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc")
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc-science")
        self.chapter = Chapter.objects.create(
            slug=next_slug("chapter"), name="Number Systems", subject=self.ict, chapter_number=1
        )

    def block(self, **overrides):
        return QuestionBlock.objects.create(**{"subject": self.ict, "chapter": self.chapter, **overrides})
