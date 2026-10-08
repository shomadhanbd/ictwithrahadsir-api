from django.urls import reverse

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.identity.models import User

WEBSITE_URL = reverse("api:website:website")
HOME_URL = reverse("api:website:home")
SECTIONS_URL = reverse("api:website:admin_section_list")
BANNERS_URL = reverse("api:website:admin_banner_list")
IMAGE = "https://example.com/banner.jpg"


def section_url(key):
    return reverse("api:website:admin_section_detail", args=[key])


class WebsiteTestCase(APITestCase):
    def setUp(self):
        self.admin = bearer(make_user(role=User.Role.ADMIN))

    def patch(self, key, body, auth=None):
        return self.client.patch(section_url(key), body, format="json", **(auth or self.admin))
