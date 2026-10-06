from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from apps.exam.models import ExamAnswer
from apps.exam.selectors import paper_questions, section_marking
from apps.exam.utils import ZERO
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


def paper_key(exam) -> PaperKey:
    questions = paper_questions(exam)
    keys = {question_id: set(ids) for question_id, ids in answer_keys(list(questions)).items()}
    required = {
        section_id: count for section_id, count in exam.sections.values_list("pk", "required_question_count") if count
    }
    return PaperKey(questions, keys, required)


def grade_attempt(attempt, paper: PaperKey | None = None):
    """Marks every answer and sets the attempt's totals; the caller saves the attempt."""
    paper = paper or paper_key(attempt.exam)
    on_paper, keys, required = paper.questions, paper.keys, paper.required
    answers = {a.question_id: a for a in attempt.answers.all()}
    # "Answer any N" sections: only the first N answers, in paper order, are marked.
    answered = Counter()

    correct = wrong = skipped = 0
    score = ZERO
    for question_id, (placement, _question) in on_paper.items():
        section_id = placement.section_id
        rates = attempt.marking.get(str(section_id), FALLBACK_RATES)
        answer = answers.get(question_id)
        chosen = set(answer.selected_option_ids) if answer else set()
        limit = required.get(section_id)
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
    skipped += sum(max(limit - answered[section_id], 0) for section_id, limit in required.items())

    ExamAnswer.objects.bulk_update(list(answers.values()), ["is_correct", "marks_awarded"])
    attempt.correct, attempt.wrong, attempt.skipped = correct, wrong, skipped
    attempt.score = score


@transaction.atomic
def regrade(exam) -> int:
    """Re-marks every submitted attempt against the current answer key."""
    count = 0
    paper = paper_key(exam)
    for attempt in exam.attempts.submitted().select_related("exam"):
        grade_attempt(attempt, paper)
        attempt.save(update_fields=["score", "correct", "wrong", "skipped", "updated_at"])
        count += 1
    return count
