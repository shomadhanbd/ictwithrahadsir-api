from django.test import TestCase
from django.urls import reverse

from apps.academic.models import Chapter, ClassLevel, Group, Subject
from apps.core.testing import bearer, make_user, next_slug
from apps.identity.models import User
from apps.question.models import QuestionBlock, QuestionSet

BLOCKS_URL = reverse("api:question:admin_question_block_list")
SAVE_URL = reverse("api:question:admin_question_block_save")
SOURCES_URL = reverse("api:question:admin_question_source_list")


def detail(resource, pk):
    return reverse(f"api:question:admin_{resource}_detail", args=[pk])


def save_question(client, auth, payload=None, *, question=None, removed=()):
    """Creates or edits one question the way the admin does, through `question-blocks/save/`.

    The block comes from the edited question, else from `block_id` or `question_set_id` in `payload`."""
    payload = dict(payload or {})
    block_id = payload.pop("block_id", None)
    set_id = payload.pop("question_set_id", None)
    if question is not None:
        block = question.block or question.question_set.block
        payload["id"] = question.pk
    elif set_id is not None:
        block = QuestionSet.objects.get(pk=set_id).block
    else:
        block = QuestionBlock.objects.get(pk=block_id)
    body = {
        "block_id": block.pk,
        "block": {},
        "questions": [payload] if payload else [],
        "removed_question_ids": list(removed),
    }
    return client.post(SAVE_URL, body, content_type="application/json", **auth)


def saved_question(response, question_id=None) -> dict:
    """The question a `save_question` response holds: the edited one, else the block's (last) question."""
    block = response.json()
    if block.get("standalone_question"):
        return block["standalone_question"]
    questions = block["question_set"]["questions"]
    return next((q for q in questions if q["id"] == question_id), questions[-1])


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

    def save_question(self, payload=None, **kwargs):
        return save_question(self.client, self.auth, payload, **kwargs)
