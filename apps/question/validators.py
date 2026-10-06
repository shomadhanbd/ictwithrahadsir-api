from django.core.exceptions import ValidationError

from apps.core import providers
from apps.question import kinds
from apps.question.models import Question, QuestionBlock, QuestionSource
from apps.question.selectors import exam_placement, owning_block


def clean_metadata(question_type, data):
    """Normalise one question's per-type settings."""
    entry = kinds.kind(question_type)
    data = data or {}

    if not isinstance(data, dict):
        raise ValidationError({"metadata": "Settings must be an object."})

    unknown = sorted(set(data) - set(entry.metadata))
    if unknown:
        raise ValidationError({"metadata": f"{entry.label} has no setting called “{unknown[0]}”."})

    cleaned = {}
    for name, spec in entry.metadata.items():
        value = data.get(name, spec.default)
        if spec.choices and value not in spec.choices:
            raise ValidationError({"metadata": f"“{name}” must be one of {', '.join(spec.choices)}."})
        cleaned[name] = value
    return cleaned


def validate_block(*, subject, chapter, kind, has_set, has_standalone, topics=()):
    """The block's own consistency: its chapter, its topics, and what its `kind` promises."""
    if chapter is not None and chapter.subject_id != subject.pk:
        raise ValidationError({"chapter": "That chapter belongs to a different subject."})

    for topic in topics:
        if chapter is None or topic.chapter_id != chapter.pk:
            raise ValidationError({"topic_ids": f"“{topic.name}” is not a topic of this question's chapter."})

    if kind == QuestionBlock.Kind.GROUP and has_standalone:
        raise ValidationError({"kind": "A group block holds a stimulus set, not one question."})
    if kind == QuestionBlock.Kind.STANDALONE and has_set:
        raise ValidationError({"kind": "A standalone block holds one question, not a stimulus set."})


def validate_single_owner(block, question_set, message="A question belongs to either a block or a set, not both."):
    if bool(block) == bool(question_set):
        raise ValidationError(message)


def validate_owner_kind(*, block=None, question_set=None):
    """A block's `kind` has to agree with what is hung off it."""
    if block is not None and block.kind != QuestionBlock.Kind.STANDALONE:
        raise ValidationError({"block_id": "That block is a group; its questions belong to its stimulus set."})
    if question_set is not None and question_set.block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"question_set_id": "A stimulus set belongs to a group block, not a standalone one."})


def validate_set_block(block):
    if block is not None and block.kind != QuestionBlock.Kind.GROUP:
        raise ValidationError({"block": "A stimulus set belongs to a group block."})


def validate_question(*, question_type, metadata, options, options_written=True):
    """What a question of this type needs before it can be marked; option text is checked when options are written."""
    kind = kinds.kind(question_type)
    settings = clean_metadata(question_type, metadata)

    positions = [option.get("position", 0) for option in options]
    if len(positions) != len(set(positions)):
        raise ValidationError({"options": "Two options share a position."})

    if not kind.uses_options:
        if options:
            raise ValidationError({"options": f"A {kind.label.lower()} takes no options."})
        return

    if options_written and sum(1 for option in options if str(option.get("content") or "").strip()) < 2:
        raise ValidationError({"options": "An MCQ needs at least two options with text."})
    correct = [option for option in options if option.get("is_correct")]
    if not correct:
        raise ValidationError({"options": "An MCQ needs at least one correct option."})
    if settings.get("select_mode") == "single" and len(correct) > 1:
        raise ValidationError({"options": "A single-answer MCQ cannot have more than one correct option."})


def _off_the_paper_first(placement):
    return f"This question is on the exam “{placement.section.exam.title}”. Take it off the paper first."


def validate_block_change(block, *, subject, kind):
    """A placed block keeps the subject and shape the exam accepted it with."""
    if block is None or (subject.pk == block.subject_id and kind == block.kind):
        return
    placement = exam_placement(block)
    if placement is not None:
        field = "subject_id" if subject.pk != block.subject_id else "kind"
        raise ValidationError({field: _off_the_paper_first(placement)})


def validate_type_change(block, *, before, after):
    """A placed block's parts keep the type its exam section holds."""
    if before == after:
        return
    placement = exam_placement(block)
    if placement is not None:
        raise ValidationError({"question_type": _off_the_paper_first(placement)})


def validate_new_part_type(block, question_type):
    placement = exam_placement(block)
    if placement is not None and placement.section.question_type != question_type:
        raise ValidationError(
            {
                "question_type": (
                    f"This question is on the exam “{placement.section.exam.title}”, "
                    f"in a {placement.section.get_question_type_display()} section."
                )
            }
        )


def validate_parts_change(block):
    """A published paper's questions keep the parts it was published with."""
    placement = exam_placement(block, published_only=True)
    if placement is not None:
        raise ValidationError(
            {
                "question_set_id": (
                    f"This question is on the published exam “{placement.section.exam.title}”. "
                    "Move the exam back to draft before adding or removing parts."
                )
            }
        )


def validate_options_kept(block, *, before_ids, options):
    """A published paper's question keeps its option rows: students' answers point at them by id."""
    after_ids = [option.get("id") for option in options]
    if len(after_ids) == len(before_ids) and set(after_ids) == set(before_ids):
        return
    placement = exam_placement(block, published_only=True)
    if placement is not None:
        raise ValidationError(
            {
                "options": (
                    f"This question is on the published exam “{placement.section.exam.title}”. "
                    "Its options can be reworded or re-marked, but not added or removed."
                )
            }
        )


def validate_editor(user, block):
    """Who may change a question already on a published paper is that paper's business."""
    check = providers.get("question.assert_may_edit_placed_block")
    if check is not None and block is not None:
        check(user, block)


def validate_question_write(instance, attrs, *, options_after_write) -> dict:
    """Every rule on a question create or update; returns `attrs` with metadata normalised."""
    block = attrs.get("block", getattr(instance, "block", None))
    question_set = attrs.get("question_set", getattr(instance, "question_set", None))
    validate_single_owner(block, question_set, "Give the question either a block or a question set, not both.")
    validate_owner_kind(block=block, question_set=question_set)

    owner = owning_block(block=block, question_set=question_set)
    if instance is None:
        validate_parts_change(owner)
        validate_new_part_type(owner, attrs.get("question_type", Question.Type.MCQ))
    else:
        previous = owning_block(block=instance.block, question_set=instance.question_set)
        if previous != owner:
            validate_parts_change(previous)
            validate_parts_change(owner)
        validate_type_change(
            owner, before=instance.question_type, after=attrs.get("question_type", instance.question_type)
        )
        if "options" in attrs:
            validate_options_kept(
                previous, before_ids=[option.pk for option in instance.options.all()], options=attrs["options"]
            )

    question_type = attrs.get("question_type", getattr(instance, "question_type", Question.Type.MCQ))
    if "metadata" in attrs or instance is None:
        attrs["metadata"] = clean_metadata(question_type, attrs.get("metadata"))
    validate_question(
        question_type=question_type,
        metadata=attrs.get("metadata", getattr(instance, "metadata", None)),
        options=options_after_write,
        options_written="options" in attrs or instance is None,
    )
    return attrs


SOURCE_DEFAULTS = {"kind": QuestionSource.Kind.BOARD, "name": "", "year": None, "unit": ""}


def validate_source_unique(instance, attrs):
    row = {
        field: attrs[field] if field in attrs else getattr(instance, field) if instance is not None else default
        for field, default in SOURCE_DEFAULTS.items()
    }
    clash = QuestionSource.objects.filter(**row)
    if instance is not None:
        clash = clash.exclude(pk=instance.pk)
    if clash.exists():
        raise ValidationError({"name": "That exam is already recorded."})
