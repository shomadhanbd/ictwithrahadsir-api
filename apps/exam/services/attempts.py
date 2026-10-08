import logging
from collections import Counter
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.core.text.bangla import bn_digits
from apps.courses.services import complete_lesson
from apps.exam.models import Exam, ExamAnswer, ExamAnswerSheet, ExamAttempt, ExamSectionQuestion
from apps.exam.selectors import assert_may_sit, is_open, lesson_exam_summary, paper_questions, valid_option_ids
from apps.exam.services.grading import frozen_marking, grade_attempt, paper_key
from apps.exam.utils import paper_seed
from apps.exam.validators import (
    validate_answers,
    validate_may_start,
    validate_required_answers,
    validate_sheet_room,
    validate_sheet_target,
)
from apps.uploads.links import public_link
from apps.uploads.validators import image_extension, pdf_extension

logger = logging.getLogger(__name__)

# Reported under `attempt`, so a client tells "this paper is closed" apart from a refused answer (`answers`).
ATTEMPT_OVER = "এই পরীক্ষা শেষ হয়ে গেছে; উত্তর আর পরিবর্তন করা যাবে না।"
ACCESS_ENDED = "এই পরীক্ষায় আপনার অ্যাক্সেস শেষ হয়েছে; সংরক্ষিত উত্তরগুলো জমা দেওয়া হয়েছে।"
# The upload checks' codes, in the students' words.
SHEET_FILE_ERRORS = {
    "too_large": "ফাইলটি সর্বোচ্চ {mb} MB হতে পারে।",
    "unreadable": "ফাইলটি পড়া যাচ্ছে না। উত্তরপত্রের একটি ছবি (JPG বা PNG) অথবা PDF দিন।",
    "wrong_type": "শুধু JPG, PNG, WebP বা GIF ছবি দেওয়া যাবে।",
    "not_pdf": "ফাইলটি PDF নয়।",
}


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


def _sheet_for(attempt, section_question_id):
    """The open attempt's answer sheet for one creative question on its paper, made on first use."""
    if not is_open(attempt):
        raise ValidationError({"attempt": ATTEMPT_OVER})
    placement = (
        ExamSectionQuestion.objects.select_related("section")
        .filter(pk=section_question_id, section__exam_id=attempt.exam_id)
        .first()
    )
    validate_sheet_target(placement)
    sheet, _ = ExamAnswerSheet.objects.select_for_update().get_or_create(attempt=attempt, section_question=placement)
    return sheet


def _sheet_file_kind(upload):
    """("pdf" | "image", extension), from the file's own content rather than the name it came with."""
    try:
        if upload.name.lower().endswith(".pdf") or getattr(upload, "content_type", "") == "application/pdf":
            return "pdf", pdf_extension(upload)
        return "image", image_extension(upload)
    except ValidationError as refused:
        problem = refused.error_dict["file"][0]
        message = SHEET_FILE_ERRORS.get(problem.code, SHEET_FILE_ERRORS["unreadable"])
        raise ValidationError({"file": message.format(mb=bn_digits((problem.params or {}).get("mb", "")))}) from None


@transaction.atomic
def add_sheet_file(attempt, section_question_id, upload):
    """Stores one photo or PDF of a handwritten answer."""
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
    sheet = _sheet_for(attempt, section_question_id)
    answered = (
        ExamAnswerSheet.objects.filter(attempt=attempt, section_question__section_id=sheet.section_question.section_id)
        .exclude(pk=sheet.pk)
        .exclude(files=[])
        .count()
    )
    validate_sheet_room(sheet, answered_in_section=answered)
    kind, extension = _sheet_file_kind(upload)
    name = default_storage.save(f"uploads/exam-answers/{attempt.pk}/{uuid4().hex}.{extension}", upload)
    sheet.files = [*sheet.files, {"link": public_link(name), "name": upload.name[:120], "kind": kind}]
    sheet.save(update_fields=["files", "updated_at"])
    return sheet


@transaction.atomic
def remove_sheet_file(attempt, section_question_id, link):
    """Takes one file off an answer sheet while the attempt is open."""
    attempt = ExamAttempt.objects.select_for_update().get(pk=attempt.pk)
    sheet = _sheet_for(attempt, section_question_id)
    kept = [item for item in sheet.files if item["link"] != link]
    if len(kept) == len(sheet.files):
        raise ValidationError({"link": "ফাইলটি এই উত্তরে নেই।"})
    sheet.files = kept
    sheet.save(update_fields=["files", "updated_at"])
    stored = link.split(default_storage.base_url, 1)[-1] if default_storage.base_url in link else None
    if stored and stored.startswith(f"uploads/exam-answers/{attempt.pk}/"):
        default_storage.delete(stored)
    return sheet
