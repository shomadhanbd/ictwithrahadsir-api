from django.test import SimpleTestCase

from apps.website.registry import PAGES, REGISTRY, SECTIONS
from apps.website.validators import clean_section_content


class RegistryTests(SimpleTestCase):
    """The registry is code, so its mistakes are caught here rather than on the live site."""

    def test_every_sections_original_copy_passes_its_own_checks(self):
        for spec in SECTIONS:
            with self.subTest(section=spec.key):
                self.assertEqual(clean_section_content(spec.key, spec.defaults), spec.defaults)

    def test_keys_are_unique_and_pages_known(self):
        self.assertEqual(len(REGISTRY), len(SECTIONS))
        pages = {key for key, _ in PAGES}
        self.assertEqual({spec.page for spec in SECTIONS} - pages, set())


class MerchantRequirementTests(SimpleTestCase):
    """SSLCommerz asks for real policy pages, a refund timeline and the business's legal details."""

    def test_each_policy_page_has_text_out_of_the_box(self):
        for slug in ("privacy-policy", "terms-and-conditions", "refund-policy"):
            with self.subTest(page=slug):
                self.assertTrue(REGISTRY[f"legal.{slug}"].defaults["body"].strip())

    def test_the_refund_policy_names_its_timeline(self):
        self.assertIn("৭–১০ কার্যদিবস", REGISTRY["legal.refund-policy"].defaults["body"])

    def test_the_brand_section_carries_the_trade_license_details(self):
        defaults = REGISTRY["site"].defaults
        self.assertEqual(defaults["trade_license"], "1230050944")
        self.assertEqual(defaults["tin"], "")
        self.assertEqual(defaults["registered_address"], "চৌহাট্টা, সিলেট।")

    def test_management_is_an_about_page_section_filled_in_by_staff(self):
        spec = REGISTRY["about.management"]
        self.assertEqual(spec.page, "about")
        self.assertEqual(spec.defaults["people"], [])

    def test_the_payment_banner_may_be_a_file_the_website_serves(self):
        self.assertEqual(REGISTRY["site"].defaults["payment_badge"], "/images/sslcommerz-banner.png")
