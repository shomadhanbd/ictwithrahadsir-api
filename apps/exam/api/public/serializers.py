from decimal import Decimal

from django.utils import timezone

from rest_framework import serializers

from apps.exam.models import ExamAttempt
from apps.exam.selectors import Standing, attempt_paper, attempt_review, results_available, written_review
from apps.question.api.public.serializers import OptionSerializer


class AttemptSummarySerializer(serializers.ModelSerializer):
    time_taken_seconds = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = ExamAttempt
        fields = [
            "id",
            "number",
            "status",
            "started_at",
            "deadline",
            "submitted_at",
            "is_official",
            "time_taken_seconds",
        ]


class AnswerItemSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    option_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=True)


class SaveAnswersSerializer(serializers.Serializer):
    answers = AnswerItemSerializer(many=True)


def paper_payload(attempt) -> list[dict]:
    payload = []
    for part in attempt_paper(attempt):
        section = part["section"]
        items = []
        for item in part["items"]:
            question_set = item["question_set"]
            stimulus = (
                {"type": question_set.stimulus_type, "content": question_set.stimulus_content}
                if question_set is not None
                else None
            )
            questions = [
                {
                    "id": row["question"].pk,
                    "label": row["question"].label,
                    "prompt_content": row["question"].prompt_content,
                    "select_mode": row["question"].select_mode,
                    "marks": row["question"].marks,
                    "options": OptionSerializer(row["options"], many=True).data,
                }
                for row in item["questions"]
            ]
            items.append({"section_question_id": item["placement"].pk, "stimulus": stimulus, "questions": questions})
        payload.append(
            {
                "id": section.pk,
                "title": section.title,
                # "mcq" is answered by choosing options; "cq" by uploading photos of a handwritten answer.
                "question_type": section.question_type,
                "instructions": section.instructions,
                # "Answer any N": saving an (N+1)th answer is refused, so the paper says N. None means all.
                "answers_required": section.required_question_count,
                "marks_per_question": part["marking"].get("positive"),
                "negative_marks": part["marking"].get("negative"),
                "items": items,
            }
        )
    return payload


def attempt_payload(attempt) -> dict:
    """An attempt with the exam it belongs to and the server's clock."""
    exam = attempt.exam
    return {
        **AttemptSummarySerializer(attempt).data,
        "server_time": timezone.now(),
        "exam": {
            "id": attempt.exam_id,
            "title": exam.title,
            "instructions": exam.instructions,
            "total_marks": exam.total_marks,
            "duration_minutes": exam.duration_minutes,
            "course_slug": exam.lesson.course.slug,
            "lesson_id": exam.lesson_id,
        },
    }


def exam_detail_payload(exam, summary, attempts) -> dict:
    return {
        **summary,
        "course": {"id": exam.lesson.course_id, "slug": exam.lesson.course.slug},
        "lesson": {"id": exam.lesson_id},
        "attempts": AttemptSummarySerializer(attempts, many=True).data,
    }


def attempt_detail_payload(attempt) -> dict:
    """The paper and the answers saved so far."""
    answers = {a.question_id: a.selected_option_ids for a in attempt.answers.all() if a.marked_at is None}
    return {
        **attempt_payload(attempt),
        "paper": paper_payload(attempt),
        "answers": [{"question_id": q, "option_ids": o} for q, o in answers.items()],
        "sheets": sheets_payload(attempt),
    }


def sheets_payload(attempt) -> list[dict]:
    return [
        {"section_question_id": sheet.section_question_id, "files": sheet.files}
        for sheet in attempt.sheets.all()
        if sheet.files
    ]


def submitted_payload(attempt) -> dict:
    exam = attempt.exam
    return {
        **attempt_payload(attempt),
        "results_available": results_available(exam),
        "result_publish_time": exam.result_publish_time,
    }


def result_payload(attempt) -> dict:
    """The MCQ part is known at once; the total and pass/fail wait until every written answer is marked."""
    exam = attempt.exam
    questions = attempt_review(attempt)
    written = written_review(attempt, reveal_answers=not attempt.awaiting_marking)
    mcq_score = sum((Decimal(q["marks_awarded"]) for q in questions), Decimal(0))
    waiting = attempt.awaiting_marking
    return {
        **attempt_payload(attempt),
        "awaiting_marking": waiting,
        "score": None if waiting else attempt.score,
        "mcq_score": mcq_score,
        "cq_score": None if waiting else attempt.score - mcq_score,
        "total_marks": exam.total_marks,
        "pass_marks": exam.pass_marks,
        "passed": None if waiting or exam.pass_marks is None else attempt.score >= exam.pass_marks,
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "skipped": attempt.skipped,
        "questions": questions,
        "written": written,
    }


def ranking_payload(total, top, mine, *, viewer, pending=0) -> dict:
    """The top official results, and the viewer's own row; each attempt carries its `rank`."""

    def row(attempt):
        return {
            "rank": attempt.rank,
            "name": attempt.user.name,
            "score": attempt.score,
            "time_taken_seconds": attempt.time_taken_seconds,
            "is_me": attempt.user_id == viewer.pk,
        }

    return {
        "total": total,
        # Official answers still waiting for a teacher's marks; they join the ranking once marked.
        "pending": pending,
        "top": [row(a) for a in top],
        "me": row(mine) if mine else None,
    }


def student_exams_payload(rows) -> dict:
    """The "My exams" list: each course exam with the student's own standing."""

    def item(row):
        exam, official = row["exam"], row["official"]
        released = row["standing"] == Standing.RESULT_AVAILABLE
        return {
            "id": exam.pk,
            "title": exam.title,
            "course": {"slug": exam.lesson.course.slug, "title": exam.lesson.course.title},
            "lesson_id": exam.lesson_id,
            "start_time": row["opens_at"],
            "end_time": exam.end_time,
            "result_publish_time": exam.result_publish_time or exam.end_time,
            "duration_minutes": exam.duration_minutes,
            "question_count": exam.question_total,
            "total_marks": exam.total_marks,
            "status": row["standing"],
            "open_attempt_id": row["open_attempt"].pk if row["open_attempt"] else None,
            "official_attempt_id": official.pk if official else None,
            "score": official.score if released and official and not official.awaiting_marking else None,
            "awaiting_marking": bool(official and official.awaiting_marking),
        }

    return {"data": [item(row) for row in rows]}
