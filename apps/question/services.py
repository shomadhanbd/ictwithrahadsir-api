"""Authoring rules for the question bank.

Here rather than in `Model.clean()` alone because `clean()` is not called by
`save()`, `bulk_create` or a DRF serializer -- the reference app put its
validation there and it never ran on the paths that mattered. Serializers call
these directly; the models call them from `clean()` so the Django admin is
covered too.

What each *type* of question needs is declared in `apps.question.types`, not
branched on here: adding a type should be a registry entry, not a new `if`.
"""

from django.core.exceptions import ValidationError

from apps.question import types
from apps.question.models import Question, QuestionBlock


def validate_block(*, subject, chapter, kind, has_set, has_standalone):
    """The block's own consistency: its chapter, and what its `kind` promises."""
    if chapter is not None and chapter.subject_id != subject.pk:
        raise ValidationError({"chapter": "That chapter belongs to a different subject."})

    if kind == QuestionBlock.Kind.GROUP and has_standalone:
        raise ValidationError({"kind": "A group block holds a stimulus set, not one question."})
    if kind == QuestionBlock.Kind.STANDALONE and has_set:
        raise ValidationError({"kind": "A standalone block holds one question, not a stimulus set."})


def validate_owner_kind(*, block=None, question_set=None):
    """A block's `kind` has to agree with what is hung off it.

    Checked here rather than only when the block itself is saved: a stimulus
    set or a question can be created long afterwards, through the API, the
    admin or a shell, and each of those is a way to contradict the `kind`.
    """
    if block is not None and block.kind != QuestionBlock.Kind.STANDALONE:
        raise ValidationError({"block_id": "That block is a group; its questions belong to its stimulus set."})
    if question_set is not None and question_set.block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"question_set_id": "A stimulus set belongs to a group block, not a standalone one."})


def validate_set_block(block):
    """A stimulus set only belongs on a group block."""
    if block is not None and block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"block": "A stimulus set belongs to a group block."})


def validate_question(*, question_type, metadata, options):
    """What a question of this type needs before it can be marked.

    An MCQ with nothing marked correct is the reference app's A5: an empty
    answer compares equal to an empty correct-set and scores full marks. Refuse
    it at authoring, where it is one message rather than a silent wrong mark.

    `options` is the set the question will *end up with* -- on a partial update
    that does not mention options, the caller passes the existing ones, so
    editing a prompt does not require resending the answer key.
    """
    kind = types.kind(question_type)
    settings = types.clean_metadata(question_type, metadata)

    # Checked for every type, not just the ones with an answer key:
    # `(question, position)` is unique, so a duplicate is a 500 from the
    # database rather than a message.
    positions = [option.get("position", 0) for option in options]
    if len(positions) != len(set(positions)):
        raise ValidationError({"options": "Two options share a position."})

    if not kind.uses_options:
        if options:
            raise ValidationError({"options": f"A {kind.label.lower()} takes no options."})
        return

    correct = [option for option in options if option.get("is_correct")]
    if not correct:
        raise ValidationError({"options": "An MCQ needs at least one correct option."})
    if settings.get("select_mode") == "single" and len(correct) > 1:
        raise ValidationError({"options": "A single-answer MCQ cannot have more than one correct option."})


def sync_question_count(block):
    """Recompute `QuestionBlock.question_count` from what is actually there.

    Driven by signals on `Question`, so it holds however the question was
    written -- serializer, Django admin or shell. The reference app moved these
    only when a backfill script ran, so an admin edit left them stale.

    Recomputed rather than incremented: an increment that misses one path
    drifts silently, and this count is small enough that correctness is free.
    """
    if block is None:
        return 0

    if block.kind == QuestionBlock.Kind.GROUP:
        count = Question.objects.filter(question_set__block=block).count()
    else:
        count = Question.objects.filter(block=block).count()

    if block.question_count != count:
        block.question_count = count
        block.save(update_fields=["question_count"])
    return count
