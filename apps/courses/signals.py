from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.courses.models import Content, ContentCompletion


@receiver(post_save, sender=Content, dispatch_uid='courses.realign_content_completions')
def realign_content_completions(sender, instance, created, **kwargs):
    """Repoint this lesson's completions if it changed course."""
    if created:
        return

    ContentCompletion.objects.filter(content=instance).exclude(course_id=instance.course_id).update(
        course_id=instance.course_id
    )
