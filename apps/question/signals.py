from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.question import services
from apps.question.models import Question, QuestionBlock
from apps.question.selectors import owning_block_id


def _affected_block_ids(instance):
    """The block it belongs to now, plus the one it was loaded from if it moved."""
    ids = {owning_block_id(instance.block_id, instance.question_set_id)}
    previous = getattr(instance, "_owner_on_load", None)
    if previous is not None:
        ids.add(owning_block_id(*previous))
    ids.discard(None)
    return ids


def _sync(block_ids):
    for block_id in block_ids:
        block = QuestionBlock.objects.filter(pk=block_id).first()
        if block is not None:
            services.sync_question_count(block)


@receiver(post_save, sender=Question, dispatch_uid="question.sync_count_on_save")
def sync_count_on_save(sender, instance, **kwargs):
    _sync(_affected_block_ids(instance))


@receiver(pre_delete, sender=Question, dispatch_uid="question.remember_owner_before_delete")
def remember_owner_before_delete(sender, instance, **kwargs):
    """Resolve the owning block while every row is still there."""
    instance._owner_block_ids = _affected_block_ids(instance)


@receiver(post_delete, sender=Question, dispatch_uid="question.sync_count_on_delete")
def sync_count_on_delete(sender, instance, **kwargs):
    _sync(getattr(instance, "_owner_block_ids", None) or _affected_block_ids(instance))
