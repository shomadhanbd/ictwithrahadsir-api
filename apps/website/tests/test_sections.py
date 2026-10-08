from django.urls import reverse

from apps.core.testing import bearer, make_user
from apps.identity.models import User
from apps.website.models import Section
from apps.website.registry import REGISTRY
from apps.website.tests.base import SECTIONS_URL, WEBSITE_URL, WebsiteTestCase, section_url


class PublicWebsiteTests(WebsiteTestCase):
    def test_every_section_shows_its_original_copy_until_edited(self):
        body = self.client.get(WEBSITE_URL).json()
        self.assertEqual(body["site"]["brand_name"], "ICT with Rahad Sir")
        self.assertEqual(body["home.hero"]["button_link"], "/course")
        self.assertEqual(len(body["syllabus"]["chapters"]), 6)
        self.assertNotIn("legal.privacy-policy", body)
        self.assertEqual(Section.objects.count(), 0)

    def test_a_hidden_section_is_left_out(self):
        self.patch("app_download", {"is_visible": False})
        self.assertNotIn("app_download", self.client.get(WEBSITE_URL).json())

    def test_site_settings_cannot_be_hidden(self):
        self.patch("site", {"is_visible": False})
        self.assertIn("site", self.client.get(WEBSITE_URL).json())

    def test_a_policy_page_is_served_alone(self):
        self.patch("legal.refund-policy", {"content": {"body": "<p>৭ দিনের মধ্যে</p><script>x()</script>"}})
        body = self.client.get(reverse("api:website:legal_page", args=["refund-policy"])).json()
        self.assertEqual(body["title"], "রিফান্ড পলিসি")
        self.assertEqual(body["body"], "<p>৭ দিনের মধ্যে</p>")
        self.assertEqual(self.client.get(reverse("api:website:legal_page", args=["nope"])).status_code, 404)


class AdminSectionTests(WebsiteTestCase):
    def test_the_admin_gets_every_section_with_its_form(self):
        body = self.client.get(SECTIONS_URL, **self.admin).json()
        self.assertEqual(len(body["data"]), len(REGISTRY))
        self.assertIn({"key": "about", "label": "About (পরিচিতি)"}, body["pages"])
        hero = next(s for s in body["data"] if s["key"] == "home.hero")
        points = next(f for f in hero["fields"] if f["name"] == "points")
        self.assertEqual((points["type"], points["max_items"]), ("list", 4))

    def test_editing_a_section_shows_on_the_site(self):
        content = {**REGISTRY["home.hero"].defaults, "badge": "নতুন ব্যাচ"}
        response = self.patch("home.hero", {"content": content})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.get(WEBSITE_URL).json()["home.hero"]["badge"], "নতুন ব্যাচ")

    def test_missing_fields_keep_their_original_copy(self):
        self.patch("about.faq", {"content": {"heading": "প্রশ্ন"}})
        faq = self.client.get(WEBSITE_URL).json()["about.faq"]
        self.assertEqual((faq["heading"], len(faq["items"])), ("প্রশ্ন", 6))

    def test_content_is_checked_against_its_fields(self):
        bad = {
            "button_link": "javascript:alert(1)",
            "points": [{"text": ""}] * 5,
            "colour": "red",
        }
        response = self.patch("home.hero", {"content": bad})
        self.assertEqual(response.status_code, 422)
        errors = response.json()["errors"]
        self.assertEqual(set(errors), {"button_link", "points", "colour"})

    def test_a_list_item_error_names_its_place(self):
        response = self.patch("about.faq", {"content": {"items": [{"question": "Q?", "answer": ""}]}})
        self.assertIn("items.0.answer", response.json()["errors"])

    def test_an_icon_must_be_one_the_site_can_draw(self):
        chapters = [{"icon": "skull", "title": "T", "topics": ""}]
        self.assertEqual(self.patch("syllabus", {"content": {"chapters": chapters}}).status_code, 422)

    def test_a_reset_restores_the_original_copy(self):
        self.patch("home.cta", {"content": {"heading": "Changed"}})
        self.client.delete(section_url("home.cta"), **self.admin)
        self.assertEqual(self.client.get(WEBSITE_URL).json()["home.cta"]["heading"], "আইসিটির প্রস্তুতি শুরু হোক আজই")

    def test_an_unknown_section_is_404(self):
        self.assertEqual(self.patch("home.nope", {"is_visible": False}).status_code, 404)

    def test_moderators_edit_the_site_and_students_do_not(self):
        moderator = bearer(make_user(role=User.Role.MODERATOR))
        self.assertEqual(self.patch("home.cta", {"is_visible": False}, moderator).status_code, 200)
        self.assertEqual(self.patch("home.cta", {"is_visible": True}, bearer(make_user())).status_code, 403)
