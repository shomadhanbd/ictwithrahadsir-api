from django.utils import timezone

from rest_framework import serializers

from apps.exam.models import ExamAttempt
from apps.exam.selectors import Standing, attempt_paper, attempt_review, results_available
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
                    "options": OptionSerializer(row["options"], many=True).data,
                }
                for row in item["questions"]
            ]
            items.append({"stimulus": stimulus, "questions": questions})
        payload.append(
            {
                "id": section.pk,
                "title": section.title,
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
            "lesson_slug": exam.lesson.slug,
        },
    }


def exam_detail_payload(exam, summary, attempts) -> dict:
    return {
        **summary,
        "course": {"id": exam.lesson.course_id, "slug": exam.lesson.course.slug},
        "lesson": {"id": exam.lesson_id, "slug": exam.lesson.slug},
        "attempts": AttemptSummarySerializer(attempts, many=True).data,
    }


def attempt_detail_payload(attempt) -> dict:
    """The paper and the answers saved so far."""
    answers = {a.question_id: a.selected_option_ids for a in attempt.answers.all()}
    return {
        **attempt_payload(attempt),
        "paper": paper_payload(attempt),
        "answers": [{"question_id": q, "option_ids": o} for q, o in answers.items()],
    }


def submitted_payload(attempt) -> dict:
    exam = attempt.exam
    return {
        **attempt_payload(attempt),
        "results_available": results_available(exam),
        "result_publish_time": exam.result_publish_time,
    }


def result_payload(attempt) -> dict:
    exam = attempt.exam
    return {
        **attempt_payload(attempt),
        "score": attempt.score,
        "total_marks": exam.total_marks,
        "pass_marks": exam.pass_marks,
        "passed": None if exam.pass_marks is None else attempt.score >= exam.pass_marks,
        "correct": attempt.correct,
        "wrong": attempt.wrong,
        "skipped": attempt.skipped,
        "questions": attempt_review(attempt),
    }


def ranking_payload(total, top, mine, *, viewer) -> dict:
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
            "lesson_slug": exam.lesson.slug,
            "start_time": row["opens_at"],
            "end_time": exam.end_time,
            "result_publish_time": exam.result_publish_time or exam.end_time,
            "duration_minutes": exam.duration_minutes,
            "question_count": exam.question_total,
            "total_marks": exam.total_marks,
            "status": row["standing"],
            "open_attempt_id": row["open_attempt"].pk if row["open_attempt"] else None,
            "official_attempt_id": official.pk if official else None,
            "score": official.score if released and official else None,
        }

    return {"data": [item(row) for row in rows]}
