from django.db.models import Max

from apps.academic.models import Topic


def next_topic_order(chapter) -> int:
    last = Topic.objects.filter(chapter=chapter).aggregate(last=Max("order"))["last"]
    return 0 if last is None else last + 1
