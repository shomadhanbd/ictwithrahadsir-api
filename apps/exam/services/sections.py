from django.db import transaction
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.selectors import block_question_count, default_pick_marks
from apps.exam.utils import ZERO
from apps.exam.validators import validate_paper_is_editable
from apps.question import kinds


def sync_section_totals(section):
    """Recompute a section's counters from the picks actually in it."""
    if section is None:
        return 0, ZERO

    counter = (
        Coalesce(Sum("block__question_count"), 0) if kinds.kind(section.question_type).counts_each_part else Count("pk")
    )
    totals = ExamSectionQuestion.objects.filter(section=section).aggregate(
        count=counter, marks=Coalesce(Sum("marks"), ZERO)
    )
    count, marks = totals["count"], totals["marks"]

    if section.question_count != count or section.computed_marks != marks:
        section.question_count = count
        section.computed_marks = marks
        section.save(update_fields=["question_count", "computed_marks"])
    return count, marks


@transaction.atomic
def reprice_section(section, *, old_rate):
    """Moves picks still at the old rate's price to the new rate; a pick priced by hand keeps its price."""
    stale = []
    for pick in section.section_questions.select_related("block"):
        parts = block_question_count(pick.block, section.question_type)
        if pick.marks == parts * old_rate:
            pick.marks = parts * section.marks_per_question
            stale.append(pick)
    ExamSectionQuestion.objects.bulk_update(stale, ["marks"])
    sync_section_totals(section)


@transaction.atomic
def reprice_block_picks(block):
    """After a block gains or loses a part, its picks on auto-marked sections cost the new count at the rate.

    Only on papers still being written: a published or attempted paper keeps the prices and totals it was set with.
    """
    editable = ExamSectionQuestion.objects.filter(block=block, section__exam__status=Exam.Status.DRAFT).exclude(
        section__exam__attempts__isnull=False
    )
    stale = []
    for pick in editable.select_related("section"):
        if kinds.kind(pick.section.question_type).auto_graded:
            marks = default_pick_marks(block, pick.section)
            if pick.marks != marks:
                pick.marks = marks
                stale.append(pick)
    ExamSectionQuestion.objects.bulk_update(stale, ["marks"])
    for section in ExamSection.objects.filter(section_questions__in=editable).distinct():
        sync_section_totals(section)


@transaction.atomic
def set_section_blocks(section, blocks, *, replace=False):
    """Adds `blocks` to the section, or makes them its whole list; kept picks keep their marks."""
    existing = {pick.block_id: pick for pick in section.section_questions.all()}

    if replace:
        section.section_questions.exclude(block_id__in={block.pk for block in blocks}).delete()

    added = [block for block in blocks if block.pk not in existing]
    if replace:
        position = {block.pk: order for order, block in enumerate(blocks)}
    else:
        position = {block.pk: len(existing) + offset for offset, block in enumerate(added)}

    ExamSectionQuestion.objects.bulk_create(
        ExamSectionQuestion(
            section=section, block=block, marks=default_pick_marks(block, section), order=position[block.pk]
        )
        for block in added
    )

    if replace:
        moved = []
        for order, block in enumerate(blocks):
            pick = existing.get(block.pk)
            if pick is not None and pick.order != order:
                pick.order = order
                moved.append(pick)
        if moved:
            ExamSectionQuestion.objects.bulk_update(moved, ["order"])

    sync_section_totals(section)
    return section


def delete_section(section):
    validate_paper_is_editable(section.exam)
    section.delete()
