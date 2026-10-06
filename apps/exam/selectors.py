from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import (
    Avg,
    Count,
    DurationField,
    ExpressionWrapper,
    F,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Window,
)
from django.db.models.functions import Coalesce, Rank
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.courses.selectors import (
    can_open_content,
    is_released,
    lesson_is_visible,
    may_manage_course,
    release_message,
)
from apps.exam.models import Exam, ExamAttempt, ExamSection, ExamSectionQuestion
from apps.exam.utils import ZERO, seeded_shuffle
from apps.exam.validators import paper_problems, section_problems
from apps.identity.roles import is_full_admin
from apps.question import kinds
from apps.question.models import QuestionBlock, QuestionOption
from apps.question.selectors import answer_keys, block_questions

AUTHOR_MESSAGE = "This exam is not yours to manage."


def may_author_exam(user, exam) -> bool:
    """An admin, the exam's author, or a teacher of the course a course exam belongs to."""
    if is_full_admin(user):
        return True
    if exam is None:
        return False
    if exam.created_by_id is not None and exam.created_by_id == user.pk:
        return True
    return exam.lesson_id is not None and may_manage_course(user, exam.lesson.course_id)


def assert_may_author_exam(user, exam):
    if not may_author_exam(user, exam):
        raise PermissionDenied(AUTHOR_MESSAGE)


def assert_may_edit_placed_block(user, block):
    """A block's questions change only for someone who may author every published paper it is on."""
    exams = (
        Exam.objects.filter(status=Exam.Status.PUBLISHED, sections__section_questions__block=block)
        .select_related("lesson")
        .distinct()
    )
    for exam in exams:
        assert_may_author_exam(user, exam)


def authored_by(queryset, user, *, exam_path=""):
    """Rows of `queryset` whose exam (reached by `exam_path`) `user` may author."""
    if is_full_admin(user):
        return queryset
    prefix = f"{exam_path}__" if exam_path else ""
    allowed = queryset.model.objects.filter(
        Q(**{f"{prefix}created_by": user}) | Q(**{f"{prefix}lesson__course__instructors__user": user})
    ).values("pk")
    return queryset.filter(pk__in=allowed)


def admin_sections():
    """Sections with their picks in order."""
    picks = ExamSectionQuestion.objects.order_by("order", "id")
    return ExamSection.objects.select_related("subject").prefetch_related(Prefetch("section_questions", queryset=picks))


def admin_exams(*, full_sections=False):
    """Exams with their totals in a fixed number of queries; `full_sections` adds each section's picks."""
    if full_sections:
        sections = Prefetch("sections", queryset=admin_sections())
    else:
        sections = Prefetch("sections", queryset=ExamSection.objects.only("exam_id", "question_type", "order"))
    return (
        Exam.objects.select_related("created_by", "batch", "lesson__course")
        .prefetch_related(sections)
        .with_admin_totals()
        .order_by("-created_at", "id")
    )


def results_available(exam, *, now=None) -> bool:
    """At the result time; with none set, once the exam closes; with neither, at once. Mirrors `results_released`."""
    release = exam.result_publish_time or exam.end_time
    return release is None or release <= (now or timezone.now())


def assert_result_visible(attempt):
    if attempt.status != ExamAttempt.Status.SUBMITTED:
        raise ValidationError({"attempt": "Submit the attempt to see its result."})
    exam = attempt.exam
    if not results_available(exam):
        when = timezone.localtime(exam.result_publish_time or exam.end_time)
        raise PermissionDenied(f"Results are released on {when:%d %b %Y, %H:%M}.")


def assert_ranking_visible(exam):
    if not results_available(exam):
        raise PermissionDenied("The ranking appears when results are released.")


def assert_may_sit(exam, user):
    """Who may see and sit a course exam."""
    if exam.scope != Exam.Scope.COURSE or exam.lesson_id is None:
        raise PermissionDenied("This exam is not taken online.")
    if exam.status != Exam.Status.PUBLISHED or not lesson_is_visible(exam.lesson):
        raise Exam.DoesNotExist
    if not is_released(exam.lesson):
        raise PermissionDenied(release_message(exam.lesson))
    if not can_open_content(user, exam.lesson):
        raise PermissionDenied("Enrol on the course to take this exam.")


def exam_for_student(slug, user):
    """A published course exam the caller may sit, or raises."""
    exam = (
        Exam.objects.course_exams()
        .select_related("lesson__course", "lesson__section__section")
        .filter(slug=slug)
        .first()
    )
    if exam is None:
        raise Exam.DoesNotExist
    assert_may_sit(exam, user)
    return exam


def is_open(attempt, *, now=None) -> bool:
    now = now or timezone.now()
    return attempt.status == ExamAttempt.Status.IN_PROGRESS and (attempt.deadline is None or now < attempt.deadline)


def paper_placements(exam):
    sections = list(exam.sections.order_by("order", "id"))
    placements = defaultdict(list)
    rows = (
        ExamSectionQuestion.objects.filter(section__exam=exam)
        .select_related("block__standalone_question", "block__question_set")
        .prefetch_related(
            "block__standalone_question__options",
            "block__question_set__questions__options",
        )
        .order_by("order", "id")
    )
    for row in rows:
        placements[row.section_id].append(row)
    return sections, placements


def paper_questions(exam):
    """`{question_id: (placement, question)}` for every question on the paper."""
    _, placements = paper_placements(exam)
    found = {}
    for rows in placements.values():
        for placement in rows:
            for question in block_questions(placement.block):
                found[question.pk] = (placement, question)
    return found


def valid_option_ids(question_ids) -> dict[int, set]:
    options = defaultdict(set)
    for option_id, question_id in QuestionOption.objects.filter(question_id__in=question_ids).values_list(
        "id", "question_id"
    ):
        options[question_id].add(option_id)
    return options


@dataclass(frozen=True)
class SectionMarking:
    positive: object
    negative: object


def section_marking(section) -> SectionMarking:
    """The rates that actually apply to one part of a paper; non-auto-graded parts lose nothing."""
    if not kinds.kind(section.question_type).auto_graded:
        return SectionMarking(section.marks_per_question, ZERO)
    return SectionMarking(section.marks_per_question, section.negative_marks or ZERO)


def block_question_count(block, question_type) -> int:
    """How many questions this block puts on a paper of this type."""
    return block.question_count if kinds.kind(question_type).counts_each_part else 1


def default_pick_marks(block, section):
    return block_question_count(block, section.question_type) * section.marks_per_question


def paper_header(*, exam, sections):
    """The block a printed প্রশ্নপত্র carries, as domain values."""
    sections = list(sections)
    computed = sum((section.target_marks for section in sections), ZERO)
    return {
        "title": exam.title,
        "instructions": exam.instructions,
        "duration_minutes": exam.duration_minutes,
        "total_marks": exam.total_marks,
        "computed_marks": computed,
        "matches_total": computed == exam.total_marks,
        "pass_marks": exam.pass_marks,
        "problems": [message for _, message in paper_problems(exam=exam, sections=sections)],
        "parts": [_paper_part(section) for section in sections],
    }


def _paper_part(section):
    answers_required = section.answers_required
    return {
        "section_id": section.pk,
        "title": section.title,
        "instructions": section.instructions,
        "question_type": section.question_type,
        "question_type_label": ExamSection.Type(section.question_type).label,
        "subject_name": section.subject.name if section.subject_id else "",
        "duration_minutes": section.duration_minutes,
        "questions_given": section.question_count,
        "answers_required": answers_required,
        "marks_per_question": section.marks_per_question,
        "marks": section.marks,
        "computed_marks": section.computed_marks,
        "target_marks": section.target_marks,
        "shows_multiplication": section.marks_per_question * answers_required == section.target_marks,
        "negative_marks": section_marking(section).negative,
        "pass_marks": section.pass_marks,
        "problems": [message for _, message in section_problems(section)],
    }


def attempt_paper(attempt) -> list[dict]:
    """The student's paper, in their own shuffled order: sections, items, questions and options."""
    sections, placements = paper_placements(attempt.exam)
    paper = []
    for section in sections:
        rows = placements[section.pk]
        if section.shuffle_questions:
            rows = seeded_shuffle(rows, seed=attempt.seed + section.pk)
        items = []
        for row in rows:
            block = row.block
            question_set = getattr(block, "question_set", None) if block.kind == QuestionBlock.Kind.GROUP else None
            questions = []
            for question in block_questions(block):
                options = list(question.options.all())
                if section.shuffle_options and options:
                    options = seeded_shuffle(options, seed=attempt.seed + question.pk)
                questions.append({"question": question, "options": options})
            items.append({"question_set": question_set, "questions": questions})
        paper.append({"section": section, "marking": attempt.marking.get(str(section.pk), {}), "items": items})
    return paper


def attempt_review(attempt) -> list[dict]:
    """Every question on the paper with the attempt's answer, the key and the explanation."""
    chosen = {a.question_id: a for a in attempt.answers.all()}
    on_paper = paper_questions(attempt.exam)
    keys = answer_keys(list(on_paper))

    review = []
    for question_id, (_placement, question) in on_paper.items():
        answer = chosen.get(question_id)
        review.append(
            {
                "id": question_id,
                "label": question.label,
                "prompt_content": question.prompt_content,
                "options": [{"id": o.pk, "label": o.label, "content": o.content} for o in question.options.all()],
                "selected_option_ids": answer.selected_option_ids if answer else [],
                "correct_option_ids": keys.get(question_id, []),
                "is_correct": answer.is_correct if answer else None,
                "marks_awarded": answer.marks_awarded if answer else 0,
                "explanation": question.explanation,
            }
        )
    return review


def official_ranks(exam) -> dict:
    """Each official attempt's rank, `{attempt pk: rank}`: higher score first, then quicker; ties share a rank.

    Reads four columns per attempt, not whole rows, so a paged table or a CSV can rank against everyone.
    """
    rows = []
    for pk, score, started_at, submitted_at in exam.attempts.official().values_list(
        "pk", "score", "started_at", "submitted_at"
    ):
        took = submitted_at - started_at if submitted_at else None
        rows.append((pk, score, took))
    rows.sort(key=lambda row: (-(row[1] or ZERO), row[2] or timezone.timedelta.max, row[0]))
    ranks, previous, rank = {}, None, 0
    for index, (pk, score, took) in enumerate(rows, start=1):
        if (score, took) != previous:
            rank, previous = index, (score, took)
        ranks[pk] = rank
    return ranks


def _timed_official(exam):
    took = ExpressionWrapper(F("submitted_at") - F("started_at"), output_field=DurationField())
    return exam.attempts.official().annotate(took=took)


def ranking(exam, viewer, *, size):
    """The top `size` official results and the viewer's own, ranked in the database as `official_ranks` ranks."""
    official = _timed_official(exam)
    order = [F("score").desc(nulls_last=True), F("took").asc()]
    top = list(
        official.select_related("user").annotate(rank=Window(Rank(), order_by=order)).order_by("rank", "pk")[:size]
    )

    mine = next((attempt for attempt in top if attempt.user_id == viewer.pk), None)
    if mine is None:
        mine = official.select_related("user").filter(user=viewer).first()
        if mine is not None:
            ahead = official.filter(Q(score__gt=mine.score) | Q(score=mine.score, took__lt=mine.took)).count()
            mine.rank = ahead + 1
    return official.count(), top, mine


def exam_result_stats(exam) -> dict:
    """The official results' figures, aggregated in the database."""
    passing = Q(score__gte=exam.pass_marks) if exam.pass_marks is not None else Q(pk__in=[])
    figures = exam.attempts.official().aggregate(
        submitted=Count("pk"),
        scored=Count("score"),
        average=Avg("score"),
        highest=Max("score"),
        passed=Count("pk", filter=passing),
    )
    scored = figures["scored"]
    return {
        "submitted": figures["submitted"],
        "in_progress": exam.attempts.in_progress().count(),
        "average": round(Decimal(figures["average"]), 2) if scored else None,
        "highest": figures["highest"] if scored else None,
        "passed": figures["passed"] if exam.pass_marks is not None and scored else None,
    }


def exam_submissions(exam, *, search=None, official_only=False):
    attempts = exam.attempts.search(search)
    if official_only:
        attempts = attempts.official()
    return attempts.results_table()


def _first(attempts, predicate: Callable):
    return next((a for a in attempts if predicate(a)), None)


def open_attempt(attempts):
    return _first(attempts, lambda a: a.status == ExamAttempt.Status.IN_PROGRESS)


def official_attempt(attempts):
    return _first(attempts, lambda a: a.is_official)


def lesson_exam_summary(content, user):
    """What a course lesson payload shows about its exam; `None` until it is published."""
    exam = Exam.objects.published().filter(lesson=content).first()
    if exam is None:
        return None

    mine = list(ExamAttempt.objects.filter(exam=exam, user=user)) if user is not None and user.is_authenticated else []
    current, official = open_attempt(mine), official_attempt(mine)
    return {
        "id": exam.pk,
        "slug": exam.slug,
        "title": exam.title,
        "instructions": exam.instructions,
        "total_marks": exam.total_marks,
        "pass_marks": exam.pass_marks,
        "duration_minutes": exam.duration_minutes,
        "start_time": exam.start_time,
        "end_time": exam.end_time,
        "result_publish_time": exam.result_publish_time,
        "question_count": exam.sections.aggregate(n=Coalesce(Sum("question_count"), 0))["n"],
        "max_attempts": exam.max_attempts,
        "attempts_used": len(mine),
        "open_attempt_id": current.pk if current else None,
        "official_attempt_id": official.pk if official else None,
        "results_available": results_available(exam),
    }


class Standing:
    """Where a student stands with one exam, as the "My exams" list groups them, in display order."""

    IN_PROGRESS = "in_progress"
    OPEN = "open"
    UPCOMING = "upcoming"
    SUBMITTED = "submitted"
    RESULT_AVAILABLE = "result_available"
    MISSED = "missed"

    ORDER = [IN_PROGRESS, OPEN, UPCOMING, SUBMITTED, RESULT_AVAILABLE, MISSED]


def _opens_at(exam):
    times = [t for t in (exam.start_time, exam.lesson.available_from) if t]
    return max(times) if times else None


def _standing(exam, mine, now) -> str:
    if open_attempt(mine):
        return Standing.IN_PROGRESS
    if official_attempt(mine):
        return Standing.RESULT_AVAILABLE if results_available(exam, now=now) else Standing.SUBMITTED
    opens = _opens_at(exam)
    if opens and opens > now:
        return Standing.UPCOMING
    if exam.end_time and exam.end_time <= now:
        return Standing.MISSED
    return Standing.OPEN


def student_exams(user, *, now=None) -> list[dict]:
    """Published course exams in the student's current courses, plus any they have sat, with their standing."""
    now = now or timezone.now()
    current = Enrollment.objects.filter(user=user).current(now).values("course_id")
    sat = ExamAttempt.objects.filter(user=user).values("exam_id")
    question_total = Subquery(
        ExamSection.objects.filter(exam=OuterRef("pk")).values("exam").annotate(n=Sum("question_count")).values("n")
    )
    exams = list(
        Exam.objects.course_exams()
        .published()
        .filter(lesson__active=True)
        .filter(Q(lesson__course_id__in=current) | Q(pk__in=sat))
        .select_related("lesson__course")
        .annotate(question_total=Coalesce(question_total, 0))
    )

    attempts = defaultdict(list)
    for attempt in ExamAttempt.objects.filter(user=user, exam__in=exams).order_by("number"):
        attempts[attempt.exam_id].append(attempt)

    rows = []
    for exam in exams:
        mine = attempts[exam.pk]
        rows.append(
            {
                "exam": exam,
                "standing": _standing(exam, mine, now),
                "open_attempt": open_attempt(mine),
                "official": official_attempt(mine),
                "opens_at": _opens_at(exam),
            }
        )
    rows.sort(key=lambda r: (Standing.ORDER.index(r["standing"]), r["opens_at"] or now, r["exam"].pk))
    return rows


def unreleased_block_ids():
    """Blocks on a paper still open or whose answers are not out yet, so practice cannot leak them."""
    # An exam with no end time can always be sat, so its questions never become free practice.
    released = Exam.objects.results_released().filter(end_time__lte=timezone.now()).values("pk")
    return ExamSectionQuestion.objects.exclude(section__exam__in=released).values("block_id")
