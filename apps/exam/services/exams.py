from django.db.models import Sum
from django.db.models.functions import Coalesce

from apps.exam.models import Exam
from apps.exam.utils import ZERO
from apps.exam.validators import validate_course_exam_deletable


def create_course_exam(lesson) -> Exam:
    """An exam lesson is an exam: adding one creates its draft paper."""
    exam, _ = Exam.objects.get_or_create(
        lesson=lesson,
        defaults={"title": lesson.title[:200], "scope": Exam.Scope.COURSE, "status": Exam.Status.DRAFT},
    )
    return exam


def sync_exam_total(exam_id) -> None:
    """The exam is worth what its sections add up to."""
    total = Exam.objects.filter(pk=exam_id).aggregate(total=Coalesce(Sum("sections__marks"), ZERO))["total"]
    Exam.objects.filter(pk=exam_id).update(total_marks=total)


def delete_exam(exam) -> None:
    validate_course_exam_deletable(exam)
    exam.delete()
