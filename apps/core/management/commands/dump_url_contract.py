"""Regenerate the URL contract snapshot guarded by apps.core.tests.

Run this ONLY when a path change is intentional, and review the resulting
diff carefully -- every line in it is a change both frontends can see.

    python manage.py dump_url_contract
"""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.url_contract import SNAPSHOT_PATH, current_url_contract


class Command(BaseCommand):
    help = 'Rewrite the URL contract snapshot from the live URLconf.'

    def handle(self, *args, **options):
        target = Path(settings.BASE_DIR) / SNAPSHOT_PATH
        paths = current_url_contract()

        previous = target.read_text().split() if target.exists() else []
        target.write_text('\n'.join(paths) + '\n')

        added = sorted(set(paths) - set(previous))
        removed = sorted(set(previous) - set(paths))

        self.stdout.write(self.style.SUCCESS(f'Wrote {len(paths)} paths to {SNAPSHOT_PATH}'))
        for path in added:
            self.stdout.write(self.style.WARNING(f'  + {path}'))
        for path in removed:
            self.stdout.write(self.style.ERROR(f'  - {path}'))
        if previous and not added and not removed:
            self.stdout.write('  (no change)')
