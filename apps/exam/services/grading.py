from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.exam.models import ExamAnswer, ExamAttempt
from apps.exam.selectors import paper_questions, section_marking, written_section_ids
from apps.exam.utils import ZERO
from apps.exam.validators import validate_written_marks
from apps.question.selectors import answer_keys

FALLBACK_RATES = {"positive": "1", "negative": "0"}  # a section added after the attempt started


def frozen_marking(exam) -> dict:
    """Each section's rates, stored on an attempt so later edits cannot change its score."""
    marking = {}
    for section in exam.sections.all():
        rates = section_marking(section)
        marking[str(section.pk)] = {"positive": str(rates.positive), "negative": str(rates.negative)}
    return marking


@dataclass(frozen=True)
class PaperKey:
    """What marking one exam needs, read once and shared by every attempt at it."""

    questions: dict  # {question_id: (placement, question)}
    keys: dict  # {question_id: {correct option ids}}
    required: dict  # {section_id: N} for "answer any N" sections
    written: set  # section ids a teacher marks by hand (CQ)


def paper_key(exam) -> PaperKey:
    questions = paper_questions(exam)
    keys = {question_id: set(ids) for question_id, ids in answer_keys(list(questions)).items()}
    required = {
        section_id: count for section_id, count in exam.sections.values_list("pk", "required_question_count") if count
    }
    return PaperKey(questions, keys, required, written_section_ids(exam))


def grade_attempt(attempt, paper: PaperKey | None = None):
    """Marks every answer and sets the attempt's totals; the caller saves the attempt.

    Options are marked against the key. A written (CQ) answer counts the marks a teacher gave its parts, and
    leaves the attempt `awaiting_marking` until every part of every uploaded answer has them.
    """
    paper = paper or paper_key(attempt.exam)
    on_paper, keys, required, written = paper.questions, paper.keys, paper.required, paper.written
    answers = {a.question_id: a for a in attempt.answers.all()}
    # "Answer any N" sections: only the first N answers, in paper order, are marked.
    answered = Counter()

    correct = wrong = skipped = 0
    score = ZERO
    graded = []
    written_parts = {}  # {placement: [question ids]}, in paper order
    for question_id, (placement, _question) in on_paper.items():
        section_id = placement.section_id
        if section_id in written:
            written_parts.setdefault(placement, []).append(question_id)
            continue
        rates = attempt.marking.get(str(section_id), FALLBACK_RATES)
        answer = answers.get(question_id)
        chosen = set(answer.selected_option_ids) if answer else set()
        limit = required.get(section_id)
        if answer:
            graded.append(answer)
        if not chosen or (limit and answered[section_id] >= limit):
            if limit is None:
                skipped += 1
            if answer:
                answer.is_correct, answer.marks_awarded = None, ZERO
            continue
        answered[section_id] += 1
        if chosen == keys.get(question_id, set()):
            correct += 1
            answer.is_correct, answer.marks_awarded = True, Decimal(rates["positive"])
        else:
            wrong += 1
            answer.is_correct, answer.marks_awarded = False, -Decimal(rates["negative"])
        score += answer.marks_awarded
    skipped += sum(
        max(limit - answered[section_id], 0) for section_id, limit in required.items() if section_id not in written
    )

    uploaded = {sheet.section_question_id for sheet in attempt.sheets.all() if sheet.files}
    awaiting = False
    for placement, question_ids in written_parts.items():
        section_id = placement.section_id
        limit = required.get(section_id)
        if placement.pk not in uploaded or (limit and answered[section_id] >= limit):
            continue
        answered[section_id] += 1
        parts = [answers.get(question_id) for question_id in question_ids]
        if all(part is not None and part.marked_at is not None for part in parts):
            score += sum((part.marks_awarded for part in parts), ZERO)
        else:
            awaiting = True

    ExamAnswer.objects.bulk_update(graded, ["is_correct", "marks_awarded"])
    attempt.correct, attempt.wrong, attempt.skipped = correct, wrong, skipped
    attempt.score = score
    attempt.awaiting_marking = awaiting


@transaction.atomic
def mark_written(attempt, marks, *, by):
    """A teacher's marks for written (CQ) parts, `[{question_id, marks}]`; re-totals the attempt."""
    attempt = ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt.pk)
    paper = paper_key(attempt.exam)
    validate_written_marks(attempt, marks, paper=paper)
    now = timezone.now()
    for item in marks:
        placement, _question = paper.questions[item["question_id"]]
        ExamAnswer.objects.update_or_create(
            attempt=attempt,
            question_id=item["question_id"],
            defaults={
                "section_question": placement,
                "marks_awarded": item["marks"],
                "is_correct": None,
                "marked_by": by,
                "marked_at": now,
            },
        )
    grade_attempt(attempt, paper)
    attempt.save(update_fields=["score", "correct", "wrong", "skipped", "awaiting_marking", "updated_at"])
    return attempt


@transaction.atomic
def regrade(exam) -> int:
    """Re-marks every submitted attempt against the current answer key."""
    count = 0
    paper = paper_key(exam)
    for attempt in exam.attempts.submitted().select_related("exam"):
        grade_attempt(attempt, paper)
        attempt.save(update_fields=["score", "correct", "wrong", "skipped", "awaiting_marking", "updated_at"])
        count += 1
    return count
