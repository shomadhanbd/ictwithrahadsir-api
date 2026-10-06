from apps.academic.models import Topic
from apps.academic.selectors import next_topic_order


def create_topic(**data) -> Topic:
    data.setdefault("order", next_topic_order(data["chapter"]))
    return Topic.objects.create(**data)
