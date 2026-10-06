from django.db import transaction
from django.db.models import Count, F, Q

from apps.academic.models import Chapter, ClassLevel, Group, Subject, Topic
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet
from apps.question.selectors import owning_block
from apps.question.validators import validate_parts_change

CURRICULUM_COUNTS = {
    ClassLevel: "subjects__question_blocks",
    Group: "subjects__question_blocks",
    Subject: "question_blocks",
    Chapter: "question_blocks",
    Topic: "question_blocks",
}


def _option_fields(option):
    return {field: value for field, value in option.items() if field != "id"}


@transaction.atomic
def create_question(data) -> Question:
    data = dict(data)
    options = data.pop("options", [])
    question = Question.objects.create(**data)
    QuestionOption.objects.bulk_create(
        QuestionOption(question=question, **_option_fields(option)) for option in options
    )
    return question


@transaction.atomic
def update_question(question, data) -> Question:
    data = dict(data)
    options = data.pop("options", None)
    for field, value in data.items():
        setattr(question, field, value)
    question.save()
    if options is not None:
        sync_options(question, options)
    return question


def sync_options(question, payloads):
    """Update the rows that are still there, add the new ones, drop the rest."""
    existing = {option.pk: option for option in question.options.all()}

    incoming = []
    for payload in payloads:
        option = existing.get(payload.get("id")) or QuestionOption(question=question)
        for field, value in _option_fields(payload).items():
            setattr(option, field, value)
        incoming.append(option)

    kept = {option.pk for option in incoming if option.pk}
    question.options.exclude(pk__in=kept).delete()

    if kept:
        # Shift kept rows clear of every target position so the unique constraint holds mid-update.
        ceiling = max([option.position for option in incoming] + [existing[pk].position for pk in kept]) + 1
        question.options.filter(pk__in=kept).update(position=F("position") + ceiling)

    for option in incoming:
        option.save()


def delete_question(question) -> None:
    validate_parts_change(owning_block(block=question.block, question_set=question.question_set))
    question.delete()


_UNSET = object()


@transaction.atomic
def save_block(block, data) -> QuestionBlock:
    """Creates (`block=None`) or updates a block with its tags and nested stimulus set."""
    data = dict(data)
    question_set = data.pop("question_set", _UNSET)
    topics, sources = data.pop("topics", None), data.pop("sources", None)

    if block is None:
        block = QuestionBlock.objects.create(**data)
    else:
        for field, value in data.items():
            setattr(block, field, value)
        block.save()
    if topics is not None:
        block.topics.set(topics)
    if sources is not None:
        block.sources.set(sources)

    if question_set is not _UNSET and question_set is not None:
        upsert_question_set(block, question_set)
    block.refresh_from_db()
    return block


def upsert_question_set(block, data) -> QuestionSet:
    question_set, created = QuestionSet.objects.get_or_create(block=block, defaults=data)
    if not created:
        for field, value in data.items():
            setattr(question_set, field, value)
        question_set.save()
    return question_set


def sync_question_count(block):
    """Recompute `QuestionBlock.question_count` from what is actually there."""
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


def refresh_curriculum_question_counts() -> None:
    """Recounts `question_count` on every curriculum row, writing only the ones that changed."""
    for model, path in CURRICULUM_COUNTS.items():
        live = Count(path, distinct=True, filter=Q(**{f"{path}__is_active": True}))  # retired blocks are not offered
        fresh = dict(model.objects.annotate(n=live).values_list("pk", "n"))
        stale = []
        for row in model.objects.only("pk", "question_count"):
            if row.question_count != fresh[row.pk]:
                row.question_count = fresh[row.pk]
                stale.append(row)
        model.objects.bulk_update(stale, ["question_count"], batch_size=500)
