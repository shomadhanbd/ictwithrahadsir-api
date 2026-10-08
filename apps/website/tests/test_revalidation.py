from unittest import mock

from django.test import override_settings

from apps.website.models import Banner
from apps.website.tests.base import IMAGE, WebsiteTestCase


class RevalidationTests(WebsiteTestCase):
    @override_settings(WEBSITE_REVALIDATE_SECRET="s3cret", FRONTEND_URL="https://site.example/")
    def test_an_edit_asks_the_website_to_refresh(self):
        with mock.patch("apps.website.services.requests.post") as post, self.captureOnCommitCallbacks(execute=True):
            self.patch("home.cta", {"is_visible": False})
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://site.example/api/revalidate")
        self.assertEqual(post.call_args.kwargs["headers"], {"X-Revalidate-Secret": "s3cret"})

    @override_settings(WEBSITE_REVALIDATE_SECRET="")
    def test_without_a_secret_nothing_is_sent(self):
        with mock.patch("apps.website.services.requests.post") as post, self.captureOnCommitCallbacks(execute=True):
            Banner.objects.create(title="A", image=IMAGE)
        post.assert_not_called()
