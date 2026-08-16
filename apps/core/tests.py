"""Guards the public URL surface against accidental drift.

The API is a drop-in replacement for a legacy Laravel contract that both
frontends call by literal path, so a refactor is only safe if it leaves
every path exactly where it was.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase

from apps.core.url_contract import SNAPSHOT_PATH, current_url_contract


class UrlContractTests(TestCase):
    def test_served_paths_match_the_snapshot(self):
        snapshot_file = Path(settings.BASE_DIR) / SNAPSHOT_PATH
        self.assertTrue(
            snapshot_file.exists(),
            f'{SNAPSHOT_PATH} is missing. Run: python manage.py dump_url_contract',
        )

        expected = snapshot_file.read_text().split()
        actual = current_url_contract()

        added = sorted(set(actual) - set(expected))
        removed = sorted(set(expected) - set(actual))

        self.assertEqual(
            (added, removed),
            ([], []),
            '\n\nThe set of served URLs changed.\n'
            f'  added:   {added or "none"}\n'
            f'  removed: {removed or "none"}\n\n'
            'Both frontends call these paths literally. If the change is\n'
            'intentional, run `python manage.py dump_url_contract` and\n'
            'review the diff; otherwise fix the routing regression.',
        )
