"""Guards the endpoints that deliberately return no pagination block."""

from django.urls import reverse

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.identity.models import User


class UnpaginatedListEnvelopeTests(APITestCase):
    """Endpoints that are deliberately unpaginated must stay that way.

    Each of these is rendered straight into a dropdown, a tree or a tab strip,
    so the client reads `data` and never looks at a pagination block. If one
    silently regains the default paginator it starts truncating at 15 rows and
    nothing else fails -- the payload still has a `data` key, just a short one.
    That is precisely what happened to the teacher lookup once, so it is
    pinned here rather than left to be noticed in production.
    """

    #: (reverse name, needs an admin token)
    ENDPOINTS = [
        ('api:courses:course_category_list', False),
        ('api:content:ebook_list', False),
        ('api:content:notice_category_list', False),
        ('api:assessment:practice_topics', False),
        ('api:profiles:admin_teacher_lookup', True),
        ('api:content:admin_page_list', True),
        ('api:identity:admin_user_search', True),
    ]

    def setUp(self):
        admin = User.objects.create_user(
            phone='01710800001',
            name='Admin',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.admin_auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

    def test_unpaginated_endpoints_return_only_a_data_key(self):
        for name, needs_admin in self.ENDPOINTS:
            with self.subTest(endpoint=name):
                auth = self.admin_auth if needs_admin else {}
                response = self.client.get(reverse(name), **auth)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.data),
                    ['data'],
                    f'{name} grew a pagination envelope; it must stay unpaginated.',
                )
