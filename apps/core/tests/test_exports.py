from django.test import SimpleTestCase

from apps.core.exports import safe_cell


class SafeCellTests(SimpleTestCase):
    def test_text_a_spreadsheet_would_run_is_quoted(self):
        for value in ("=1+1", "+880171", "-2+3", "@SUM(A1)", "\tx", "\rx"):
            with self.subTest(value=value):
                self.assertEqual(safe_cell(value), f"'{value}")

    def test_ordinary_values_are_left_alone(self):
        for value in ("Rahim", "রহিম", "", 0, -0.25, None):
            with self.subTest(value=value):
                self.assertEqual(safe_cell(value), value)
