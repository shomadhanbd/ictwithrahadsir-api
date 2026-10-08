"""Who may use the question bank."""

from apps.core.testing import bearer, make_user
from apps.identity.models import User
from apps.question.tests.base import BLOCKS_URL, QuestionTestCase, detail


class PermissionTests(QuestionTestCase):
    """Teaching staff share the bank; everyone else is refused."""

    def setUp(self):
        super().setUp()
        self.solo = self.block()

    def _urls(self):
        return [
            BLOCKS_URL,
            detail("question_block", self.solo.pk),
        ]

    def test_a_student_is_refused(self):
        auth = bearer(make_user())
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_a_teacher_may_author_the_bank(self):
        auth = bearer(make_user(role=User.Role.TEACHER))

        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 200, url)

        created = self.client.post(
            BLOCKS_URL,
            {"subject_id": self.ict.pk, "kind": "standalone"},
            content_type="application/json",
            **auth,
        )
        self.assertEqual(created.status_code, 201)

    def test_a_moderator_is_refused(self):
        auth = bearer(make_user(role=User.Role.MODERATOR))
        for url in self._urls():
            self.assertEqual(self.client.get(url, **auth).status_code, 403, url)

    def test_an_anonymous_caller_is_refused(self):
        for url in self._urls():
            self.assertEqual(self.client.get(url).status_code, 401, url)
