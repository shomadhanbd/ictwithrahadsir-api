from django.db import transaction
from django.db.models import Max

from apps.academic import curriculum
from apps.academic.models import ClassLevel, Group, Subject, Topic


def create_topic(**data) -> Topic:
    """Adds a topic; without an explicit `order` it goes last in its chapter."""
    if "order" not in data:
        last = Topic.objects.filter(chapter=data["chapter"]).aggregate(last=Max("order"))["last"]
        data["order"] = 0 if last is None else last + 1
    return Topic.objects.create(**data)


@transaction.atomic
def seed_curriculum() -> dict:
    """Adds the board's class levels, groups and subjects that are missing; rows already there are left as edited."""
    created = {"class levels": 0, "groups": 0, "subjects": 0}

    levels = {}
    for order, (name, slug) in enumerate(curriculum.CLASS_LEVELS):
        levels[slug], new = ClassLevel.objects.get_or_create(slug=slug, defaults={"name": name, "order": order})
        created["class levels"] += new

    groups = {}
    for order, (name, slug, is_common) in enumerate(curriculum.GROUPS):
        groups[slug], new = Group.objects.get_or_create(
            slug=slug, defaults={"name": name, "order": order, "is_common": is_common}
        )
        created["groups"] += new

    for level_slug, by_group in curriculum.SUBJECTS.items():
        order = 0
        for group_slug, subjects in by_group.items():
            for name, stem in subjects:
                _, new = Subject.objects.get_or_create(
                    slug=f"{stem}-{level_slug}-{group_slug}",
                    defaults={
                        "name": name,
                        "class_level": levels[level_slug],
                        "group": groups[group_slug],
                        "order": order,
                    },
                )
                created["subjects"] += new
                order += 1
    return created
