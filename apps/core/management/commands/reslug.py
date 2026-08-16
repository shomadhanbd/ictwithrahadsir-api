"""Backfill slugs that the old ASCII-only `slugify()` mangled.

Before `apps.core.slugs.ascii_slug`, a Bangla title slugified to an empty
string and fell back to a shared literal, so rows ended up as "item",
"item-2", "product-3" and so on. This regenerates those slugs from their
titles.

    python manage.py reslug              # dry run, prints proposed changes
    python manage.py reslug --apply      # actually write them
    python manage.py reslug --all        # revisit every row, not just broken ones

Changing a slug changes that row's public URL, so this is opt-in and dry-run
by default. Old URLs are not redirected -- if the site is already indexed,
weigh the SEO cost before applying to production.
"""

import re

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.content.models import Notice, NoticeCategory
from apps.core.slugs import ascii_slug
from apps.courses.models import Content, Course, CourseCategory, Section
from apps.billing.models import Product

# Slugs the old code produced when it had nothing usable to work with.
BROKEN = re.compile(r"^(item|product)(-\d+)?$")

# (model, source field). Section slugs were derived from "<course_id>-<title>".
TARGETS = [
    (CourseCategory, "title"),
    (Course, "title"),
    (Section, "title"),
    (Content, "title"),
    (NoticeCategory, "title"),
    (Notice, "title"),
    (Product, "name"),
]


class Command(BaseCommand):
    help = "Regenerate slugs that fell back to 'item'/'product' under the old slugify."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true",
                            help="Write the new slugs (default is a dry run).")
        parser.add_argument("--all", action="store_true",
                            help="Consider every row, not just broken slugs.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        consider_all = options["all"]
        total = 0

        with transaction.atomic():
            for model, source_field in TARGETS:
                taken = set(model.objects.values_list("slug", flat=True))
                changes = []

                for obj in model.objects.all():
                    if not consider_all and not BROKEN.match(obj.slug or ""):
                        continue

                    base = ascii_slug(getattr(obj, source_field) or "")
                    if model is Section:
                        base = ascii_slug(f"{obj.course_id}-{getattr(obj, source_field)}")

                    if base == obj.slug:
                        continue

                    candidate, n = base, 1
                    while candidate in taken:
                        n += 1
                        candidate = f"{base}-{n}"

                    taken.discard(obj.slug)
                    taken.add(candidate)
                    changes.append((obj, obj.slug, candidate))

                if not changes:
                    continue

                self.stdout.write(self.style.MIGRATE_HEADING(
                    f"\n{model.__name__} ({len(changes)})"))
                for obj, old, new in changes:
                    self.stdout.write(f"  {old or '(blank)':<24} -> {new}")
                    if apply_changes:
                        obj.slug = new
                        obj.save(update_fields=["slug"])
                total += len(changes)

            if not apply_changes:
                transaction.set_rollback(True)

        if total == 0:
            self.stdout.write(self.style.SUCCESS("\nNo slugs need changing."))
        elif apply_changes:
            self.stdout.write(self.style.SUCCESS(f"\nRewrote {total} slugs."))
        else:
            self.stdout.write(self.style.WARNING(
                f"\nDry run: {total} slugs would change. Re-run with --apply to write them."))
