from apps.exam.models import Exam
from apps.exam.validators import validate_course_exam_deletable


def create_course_exam(lesson) -> Exam:
    """An exam lesson is an exam: adding one creates its draft paper."""
    exam, _ = Exam.objects.get_or_create(
        lesson=lesson,
        defaults={"title": lesson.title[:200], "scope": Exam.Scope.COURSE, "status": Exam.Status.DRAFT},
    )
    return exam


def delete_exam(exam) -> None:
    validate_course_exam_deletable(exam)
    exam.delete()
