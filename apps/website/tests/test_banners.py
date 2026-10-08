from django.urls import reverse
from django.utils import timezone

from apps.website.models import Banner
from apps.website.tests.base import BANNERS_URL, HOME_URL, IMAGE, WebsiteTestCase


class BannerTests(WebsiteTestCase):
    def test_banners_are_added_in_order_and_move(self):
        for title in ("A", "B"):
            body = {"title": title, "image": IMAGE, "link": "/course"}
            self.assertEqual(self.client.post(BANNERS_URL, body, format="json", **self.admin).status_code, 201)
        second = Banner.objects.get(title="B")
        url = reverse("api:website:admin_banner_move", args=[second.pk])
        self.client.post(url, {"direction": "up"}, format="json", **self.admin)
        self.assertEqual([b["title"] for b in self.client.get(HOME_URL).json()["banners"]], ["B", "A"])

    def test_only_active_banners_within_their_dates_show(self):
        now = timezone.now()
        Banner.objects.create(title="Live", image=IMAGE)
        Banner.objects.create(title="Off", image=IMAGE, is_active=False)
        Banner.objects.create(title="Later", image=IMAGE, starts_at=now + timezone.timedelta(days=1))
        Banner.objects.create(title="Over", image=IMAGE, ends_at=now - timezone.timedelta(days=1))
        self.assertEqual([b["title"] for b in self.client.get(HOME_URL).json()["banners"]], ["Live"])

    def test_a_banner_ends_after_it_starts(self):
        now = timezone.now().isoformat()
        body = {"title": "X", "image": IMAGE, "starts_at": now, "ends_at": now}
        response = self.client.post(BANNERS_URL, body, format="json", **self.admin)
        self.assertEqual(response.status_code, 422)
        self.assertIn("ends_at", response.json()["errors"])
