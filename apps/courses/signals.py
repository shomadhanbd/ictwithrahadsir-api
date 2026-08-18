"""Keeps a lesson's completion rows pointing at the lesson's own course.

`ContentCompletion` stores `course` alongside `content` so progress can be
counted without joining through the section tree, and its `save()` forces the
two to agree. That guard only fires when the *completion* is saved, though:
moving a `Content` to another course left every existing completion pointing
at the old one.

The effect is not cosmetic. `apps/courses/selectors.py::course_progress`
counts completions by course, so a moved lesson silently kept crediting
students on the course it left and never credited them on the one it joined.

Signal rather than service for the same reason as `apps/faculty/signals.py`:
a `Content` is saved from `AdminContentViewSet` (a `ModelViewSet`), the
Django admin and the seed command, with no shared chokepoint to hang a
service call on.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.courses.models import Content, ContentCompletion


@receiver(post_save, sender=Content, dispatch_uid='courses.realign_content_completions')
def realign_content_completions(sender, instance, created, **kwargs):
    """Repoint this lesson's completions if it changed course."""
    if created:
        # Nothing can have completed a lesson that did not exist.
        return

    ContentCompletion.objects.filter(content=instance).exclude(
        course_id=instance.course_id
    ).update(course_id=instance.course_id)
