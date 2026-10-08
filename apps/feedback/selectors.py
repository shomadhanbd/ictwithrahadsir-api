from django.db.models import Avg, Count
from django.shortcuts import get_object_or_404

from apps.courses.models import Course
from apps.feedback.models import Feedback


def published_feedback():
    return Feedback.objects.filter(status=Feedback.Status.APPROVED).select_related("course")


def featured_feedback():
    return published_feedback().filter(is_featured=True)


def course_rating(course) -> dict:
    """Average, count and how many gave each star, over approved feedback."""
    feedback = published_feedback().filter(course=course)
    totals = feedback.aggregate(average=Avg("rating"), count=Count("id"))
    stars = dict(feedback.values_list("rating").annotate(n=Count("id")))
    return {
        "average": round(totals["average"], 1) if totals["average"] is not None else None,
        "count": totals["count"],
        "distribution": {str(star): stars.get(star, 0) for star in range(5, 0, -1)},
    }


def my_feedback(user, *, course=None):
    source = Feedback.Source.COURSE if course else Feedback.Source.GENERAL
    return Feedback.objects.filter(author=user, source=source, course=course).select_related("course").first()


def admin_feedback():
    return Feedback.objects.select_related("course", "author")


def feedback_course(slug):
    """A course students can still give feedback on (published or archived), or 404."""
    return get_object_or_404(Course.objects.available(), slug=slug)
