"""Keeps `ExamSection.question_count` and `.computed_marks` true.

They move when a pick is added, moved or removed -- and when a picked block
gains or loses a part, since an MCQ section counts every part of a passage.

A signal rather than a service call, because a pick is written from the admin
API, the Django admin and the shell, with no single chokepoint to hang one on.

`bulk_create` and queryset `.update()` / `.delete()` bypass every signal, so
the bulk picker calls `services.sync_section_totals` itself.
"""

from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.exam import services
from apps.exam.models import ExamSection, ExamSectionQuestion
from apps.question.models import QuestionBlock


def _affected_section_ids(instance):
    """Where the pick is now, plus where it came from if it moved."""
    ids = {instance.section_id, getattr(instance, "_section_on_load", None)}
    ids.discard(None)
    return ids


def _sync(section_ids):
    """Recount each section, skipping any that is already gone.

    By id, not through `instance.section`: a moved pick has two sections to fix
    and the instance carries only the new one.
    """
    for section_id in section_ids:
        section = ExamSection.objects.filter(pk=section_id).first()
        if section is not None:
            services.sync_section_totals(section)


@receiver(post_save, sender=ExamSectionQuestion, dispatch_uid="exam.sync_totals_on_save")
def sync_totals_on_save(sender, instance, **kwargs):
    _sync(_affected_section_ids(instance))


@receiver(pre_delete, sender=ExamSectionQuestion, dispatch_uid="exam.remember_section_before_delete")
def remember_section_before_delete(sender, instance, **kwargs):
    """Resolve the section while every row is still there.

    Every `pre_delete` is sent before the first row goes, so this is early
    enough whatever order the collector then picks.
    """
    instance._section_ids = _affected_section_ids(instance)


@receiver(post_delete, sender=ExamSectionQuestion, dispatch_uid="exam.sync_totals_on_delete")
def sync_totals_on_delete(sender, instance, **kwargs):
    # After, not in `pre_delete`: the row has to be gone before it is recounted.
    _sync(getattr(instance, "_section_ids", None) or _affected_section_ids(instance))


@receiver(post_save, sender=QuestionBlock, dispatch_uid="exam.sync_totals_on_block_parts")
def sync_totals_on_block_parts(sender, instance, update_fields=None, **kwargs):
    """A picked block's part count changed (`question.services.sync_question_count`).

    Only the sections this block sits in are recounted -- a handful of rows.
    """
    if update_fields is None or "question_count" not in update_fields:
        return
    for section in ExamSection.objects.filter(section_questions__block=instance).distinct():
        services.sync_section_totals(section)
