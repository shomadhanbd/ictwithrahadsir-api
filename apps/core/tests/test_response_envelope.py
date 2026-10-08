"""Guards the endpoints that deliberately return no pagination block."""

from django.urls import reverse

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.identity.models import User


class UnpaginatedListEnvelopeTests(APITestCase):
    """Endpoints that are deliberately unpaginated must stay that way."""

    #: (reverse name, needs an admin token)
    ENDPOINTS = [
        ('api:materials:library', False),
        ('api:communication:notice_category_list', False),
        ('api:profiles:admin_teacher_lookup', True),
        ('api:website:admin_banner_list', True),
        ('api:identity:admin_user_search', True),
    ]

    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.admin_auth = bearer(admin)

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
