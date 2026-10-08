from urllib.parse import urlparse

from django.core.exceptions import ValidationError

from apps.materials.models import MaterialItem, MaterialTopic

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def validate_item(*, kind, url, price):
    if kind == MaterialItem.Kind.BOOK:
        if not price:
            raise ValidationError({"price": "Set the book's price."})
        return
    if not url:
        raise ValidationError({"url": "Add the link."})
    if kind == MaterialItem.Kind.VIDEO and urlparse(url).hostname not in YOUTUBE_HOSTS:
        raise ValidationError({"url": "A video must be a YouTube link."})


def validate_topic_access(*, access, courses):
    if access == MaterialTopic.Access.ENROLLED and not courses:
        raise ValidationError({"course_ids": "Choose the courses whose students may open this topic."})
