from django.db.models import Max

from apps.academic.models import Topic


def create_topic(**data) -> Topic:
    """Adds a topic; without an explicit `order` it goes last in its chapter."""
    if "order" not in data:
        last = Topic.objects.filter(chapter=data["chapter"]).aggregate(last=Max("order"))["last"]
        data["order"] = 0 if last is None else last + 1
    return Topic.objects.create(**data)
