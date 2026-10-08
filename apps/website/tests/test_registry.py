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
