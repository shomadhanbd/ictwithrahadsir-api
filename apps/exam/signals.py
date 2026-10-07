from decimal import Decimal

from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.exam.models import ExamSection, ExamSectionQuestion
from apps.exam.services.exams import create_course_exam, sync_exam_total
from apps.exam.services.sections import reprice_block_picks, reprice_section, sync_section_totals
from apps.question.models import QuestionBlock


def _affected_section_ids(instance):
    """Where the pick is now, plus where it came from if it moved."""
    ids = {instance.section_id, getattr(instance, "_section_on_load", None)}
    ids.discard(None)
    return ids


def _sync(section_ids):
    """Recount each section, skipping any that is already gone."""
    for section_id in section_ids:
        section = ExamSection.objects.filter(pk=section_id).first()
        if section is not None:
            sync_section_totals(section)


@receiver(post_save, sender=ExamSectionQuestion, dispatch_uid="exam.sync_totals_on_save")
def sync_totals_on_save(sender, instance, **kwargs):
    _sync(_affected_section_ids(instance))


@receiver(pre_delete, sender=ExamSectionQuestion, dispatch_uid="exam.remember_section_before_delete")
def remember_section_before_delete(sender, instance, **kwargs):
    """Resolve the section while every row is still there."""
    instance._section_ids = _affected_section_ids(instance)


@receiver(post_delete, sender=ExamSectionQuestion, dispatch_uid="exam.sync_totals_on_delete")
def sync_totals_on_delete(sender, instance, **kwargs):
    _sync(getattr(instance, "_section_ids", None) or _affected_section_ids(instance))


@receiver(pre_save, sender=ExamSection, dispatch_uid="exam.remember_section_rate")
def remember_section_rate(sender, instance, update_fields=None, **kwargs):
    """The rate as saved, read from the database so it holds however the section was loaded."""
    instance._saved_rate = None
    if instance.pk is None or (update_fields is not None and "marks_per_question" not in update_fields):
        return
    instance._saved_rate = (
        ExamSection.objects.filter(pk=instance.pk).values_list("marks_per_question", flat=True).first()
    )


@receiver(post_save, sender=ExamSection, dispatch_uid="exam.reprice_on_section_rate")
def reprice_on_section_rate(sender, instance, created, **kwargs):
    """Re-prices the picks when the section's marks per question changed."""
    old_rate = getattr(instance, "_saved_rate", None)
    if created or old_rate is None or old_rate == Decimal(instance.marks_per_question):
        return
    reprice_section(instance, old_rate=old_rate)


@receiver(post_save, sender=ExamSection, dispatch_uid="exam.sync_exam_total_on_section_save")
@receiver(post_delete, sender=ExamSection, dispatch_uid="exam.sync_exam_total_on_section_delete")
def sync_exam_total_on_section_change(sender, instance, **kwargs):
    sync_exam_total(instance.exam_id)


@receiver(post_save, sender=QuestionBlock, dispatch_uid="exam.sync_totals_on_block_parts")
def sync_totals_on_block_parts(sender, instance, update_fields=None, **kwargs):
    """Re-prices and re-totals the sections a block sits in when its part count changes."""
    if update_fields is None or "question_count" not in update_fields:
        return
    reprice_block_picks(instance)


@receiver(post_save, sender="courses.Content", dispatch_uid="exam.create_course_exam")
def create_exam_for_lesson(sender, instance, created, **kwargs):
    if created and instance.type == instance.Type.EXAM:
        create_course_exam(instance)
