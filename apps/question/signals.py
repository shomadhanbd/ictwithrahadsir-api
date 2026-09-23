"""Keeps `QuestionBlock.question_count` true however a question was written.

The count was maintained in the serializer, which is one of at least four ways
a question is created or removed: the admin API, the Django admin (and its
inline), a shell session and a data migration. Anything but the first left the
count stale -- and a `DELETE` through the API left it stale too, because
`destroy()` never went through the serializer at all.

Signal rather than service, for the same reason as `courses.signals`: there is
no single chokepoint to hang a service call on. `bulk_create` and queryset
`.update()` / `.delete()` still bypass this, as they bypass every signal; an
importer has to call `services.sync_question_count` itself.
"""

from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import receiver

from apps.question import services
from apps.question.models import Question, QuestionBlock, QuestionSet


def _owning_block_id(block_id, question_set_id):
    if block_id:
        return block_id
    if question_set_id:
        return QuestionSet.objects.filter(pk=question_set_id).values_list("block_id", flat=True).first()
    return None


def _affected_block_ids(instance):
    """The block it belongs to now, plus the one it was loaded from if it moved."""
    ids = {_owning_block_id(instance.block_id, instance.question_set_id)}
    previous = getattr(instance, "_owner_on_load", None)
    if previous is not None:
        ids.add(_owning_block_id(*previous))
    ids.discard(None)
    return ids


def _sync(block_ids):
    for block_id in block_ids:
        # Refetched rather than followed through the FK: a block being deleted
        # loses its questions first, and saving a row that is about to
        # disappear raises "Save with update_fields did not affect any rows".
        block = QuestionBlock.objects.filter(pk=block_id).first()
        if block is not None:
            services.sync_question_count(block)


@receiver(post_save, sender=Question, dispatch_uid="question.sync_count_on_save")
def sync_count_on_save(sender, instance, **kwargs):
    _sync(_affected_block_ids(instance))


@receiver(pre_delete, sender=Question, dispatch_uid="question.remember_owner_before_delete")
def remember_owner_before_delete(sender, instance, **kwargs):
    """Resolve the owning block while every row is still there.

    A cascade deletes a `QuestionSet` *before* the questions hanging off it, so
    a question's `post_delete` has nothing left to follow back to the block. The
    collector sends every `pre_delete` before it removes the first row, which is
    early enough.
    """
    instance._owner_block_ids = _affected_block_ids(instance)


@receiver(post_delete, sender=Question, dispatch_uid="question.sync_count_on_delete")
def sync_count_on_delete(sender, instance, **kwargs):
    # Recounted here rather than in `pre_delete`: the row has to be gone first.
    _sync(getattr(instance, "_owner_block_ids", None) or _affected_block_ids(instance))
