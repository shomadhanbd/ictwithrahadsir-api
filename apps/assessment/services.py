"""Marking and submitting exam papers.

`score_paper` is deliberately pure -- answers and two mark values in, a total
out -- so the marking rules can be tested directly without building a request,
an enrolment and an exam first.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction

from rest_framework.exceptions import ValidationError

from apps.assessment.models import ExamAttempt, Question


def _question_id(answer):
    """The referenced question id, or None if it isn't one.

    The client sends whatever it likes here; a non-numeric id used to reach
    the ORM and raise ValueError, i.e. a 500 that lost the whole submission.
    It is now simply an answer that matches no question.
    """
    try:
        return int(answer.get('mcq_id'))
    except (TypeError, ValueError):
        return None


def _flatten_answers(sections):
    """(question_id, normalised answer) for every answer in every section."""
    return [
        (_question_id(answer), (answer.get('user_answer') or '').strip().lower())
        for section in sections
        if isinstance(section, dict)
        for answer in section.get('answers', [])
        if isinstance(answer, dict)
    ]


def score_paper(sections, positive: Decimal, negative: Decimal) -> Decimal:
    """Mark a submitted paper.

    A correct answer scores `positive`, a wrong one loses `negative`, and an
    unanswered question scores nothing. Answers that reference no real
    question are ignored rather than treated as wrong.

    The answer keys are fetched in one query rather than one per question: a
    100-question paper used to issue 100 SELECTs on submit, at the exact
    moment a whole class hits the endpoint together.
    """
    submitted = _flatten_answers(sections)
    keys = dict(
        Question.objects.filter(pk__in={qid for qid, _ in submitted if qid is not None}).values_list('id', 'answer')
    )

    total = Decimal('0')
    for qid, user_answer in submitted:
        correct = keys.get(qid)
        if correct is None or not user_answer:
            continue
        total += positive if user_answer == correct else -negative
    return total


def submit_exam(*, exam, user, sections, duration: int = 0) -> ExamAttempt:
    """Sit an exam once and record the marks.

    An exam may be taken once. `ExamAttempt` already carries a
    `unique_together` on (exam, user), so the pre-check below is a courtesy
    that produces a readable validation error; the `IntegrityError` branch is
    what actually holds when two submissions arrive together and both clear
    that check. Without it the loser of the race got a 500 and lost the paper.
    """
    if ExamAttempt.objects.filter(exam=exam, user=user).exists():
        raise ValidationError({'exam': ['You have already submitted this exam.']})

    positive = exam.positive_marks or Decimal('1')
    negative = exam.negative_marks or Decimal('0')
    marks = score_paper(sections, positive, negative)

    try:
        # The INSERT gets its own atomic block so the `IntegrityError` can be
        # caught safely: if this is ever called from inside another
        # transaction, a failed statement poisons the whole block and the
        # ValidationError below would become unraisable. There is only one
        # write here, so no wider transaction is needed.
        with transaction.atomic():
            return ExamAttempt.objects.create(
                exam=exam,
                user=user,
                marks=marks,
                positive_marks=positive,
                negative_marks=negative,
                duration=duration,
                submitted=True,
                answers=sections,
            )
    except IntegrityError:
        raise ValidationError({'exam': ['You have already submitted this exam.']})
