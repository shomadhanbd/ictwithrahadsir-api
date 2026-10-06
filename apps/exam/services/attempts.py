import logging
from collections import Counter

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.courses.services import complete_lesson
from apps.exam.models import Exam, ExamAnswer, ExamAttempt
from apps.exam.selectors import assert_may_sit, is_open, lesson_exam_summary, paper_questions, valid_option_ids
from apps.exam.services.grading import frozen_marking, grade_attempt, paper_key
from apps.exam.utils import paper_seed
from apps.exam.validators import validate_answers, validate_may_start, validate_required_answers

logger = logging.getLogger(__name__)

# Reported under `attempt`, so a client tells "this paper is closed" apart from a refused answer (`answers`).
ATTEMPT_OVER = "This attempt is over; answers can no longer change."
ACCESS_ENDED = "Your access to this exam has ended; the answers you saved were submitted."


def _deadline(exam, started_at):
    ends = [exam.end_time] if exam.end_time else []
    if exam.duration_minutes:
        ends.append(started_at + timezone.timedelta(minutes=exam.duration_minutes))
    return min(ends) if ends else None


@transaction.atomic
def start_attempt(exam, user, *, now=None):
    """The student's open attempt, or a new one if they may start one."""
    now = now or timezone.now()
    assert_may_sit(exam, user)

    Exam.objects.select_for_update().filter(pk=exam.pk).first()  # serialises concurrent starts

    mine = ExamAttempt.objects.filter(exam=exam, user=user)
    finalize_expired(mine, now=now)

    current = mine.in_progress().first()
    if current is not None:
        return current

    used = mine.aggregate(n=Max("number"))["n"] or 0
    validate_may_start(exam, used=used, now=now)

    number = used + 1
    return ExamAttempt.objects.create(
        exam=exam,
        user=user,
        number=number,
        seed=paper_seed(exam_id=exam.pk, user_id=f"{user.pk}:{number}"),
        started_at=now,
        deadline=_deadline(exam, now),
        marking=frozen_marking(exam),
    )


def finalize_expired(attempts, *, now=None) -> int:
    """Submits, as they stand, any of `attempts` whose time has run out; each exam's paper is read once."""
    papers = {}
    count = 0
    for attempt in attempts.expired(now).select_related("exam"):
        try:
            if attempt.exam_id not in papers:
                papers[attempt.exam_id] = paper_key(attempt.exam)
            submit(attempt, now=attempt.deadline, paper=papers[attempt.exam_id])
        except Exception:
            # One broken attempt must not stall every other one, run after run.
            logger.exception("Could not finalize exam attempt %s", attempt.pk)
            continue
        count += 1
    return count


def settled(attempts):
    """`attempts` after any whose time ran out have been submitted."""
    finalize_expired(attempts)
    return attempts


def own_attempt(user, pk) -> ExamAttempt:
    """The caller's attempt, submitted first if its time has run out."""
    attempt = ExamAttempt.objects.select_related("exam__lesson__course", "exam__lesson__section__section").get(
        pk=pk, user=user
    )
    finalize_expired(ExamAttempt.objects.filter(pk=attempt.pk))
    attempt.refresh_from_db()
    return attempt


def end_if_access_lost(attempt, user):
    """Submits, as it stands, an attempt whose student may no longer sit the exam (enrolment ended, lesson
    switched off), rather than leaving it open but unable to save."""
    try:
        assert_may_sit(attempt.exam, user)
    except (PermissionDenied, Exam.DoesNotExist):
        submit(attempt)
        raise ValidationError({"attempt": ACCESS_ENDED}) from None


@transaction.atomic
def save_answers(attempt, answers, *, now=None):
    """Upserts `[{question_id, option_ids}]` for an open attempt."""
    now = now or timezone.now()
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
    if not is_open(attempt, now=now):
        raise ValidationError({"attempt": ATTEMPT_OVER})

    on_paper = paper_questions(attempt.exam)
    wanted = {item["question_id"]: sorted(set(item.get("option_ids", []))) for item in answers}
    validate_answers(wanted, on_paper=on_paper, valid_options=valid_option_ids(list(wanted)))
    chosen = {**dict(attempt.answers.values_list("question_id", "selected_option_ids")), **wanted}
    answered = Counter(on_paper[q][0].section_id for q, ids in chosen.items() if ids and q in on_paper)
    validate_required_answers(answered, sections=attempt.exam.sections.all())

    for question_id, option_ids in wanted.items():
        placement, _question = on_paper[question_id]
        ExamAnswer.objects.update_or_create(
            attempt=attempt,
            question_id=question_id,
            defaults={"section_question": placement, "selected_option_ids": option_ids},
        )
    return attempt


@transaction.atomic
def submit(attempt, *, now=None, paper=None):
    """Closes and grades an attempt; the first one submitted is the official one."""
    now = now or timezone.now()
    attempt = ExamAttempt.objects.select_for_update().select_related("exam").get(pk=attempt.pk)
    if attempt.status == ExamAttempt.Status.SUBMITTED:
        return attempt

    grade_attempt(attempt, paper)
    attempt.status = ExamAttempt.Status.SUBMITTED
    attempt.submitted_at = min(now, attempt.deadline) if attempt.deadline else now
    attempt.is_official = not ExamAttempt.objects.filter(exam=attempt.exam, user=attempt.user).official().exists()
    attempt.save()
    if attempt.exam.lesson_id:
        complete_lesson(user=attempt.user, content=attempt.exam.lesson)
    return attempt


def lesson_exam(content, user):
    """Settles the viewer's expired attempts, then summarises the lesson's exam."""
    if user is not None and user.is_authenticated:
        finalize_expired(ExamAttempt.objects.filter(exam__lesson=content, user=user))
    return lesson_exam_summary(content, user)
