from django_filters import rest_framework as filters

from apps.feedback.models import Feedback


class FeedbackFilter(filters.FilterSet):
    source = filters.ChoiceFilter(choices=Feedback.Source.choices)
    course = filters.CharFilter(field_name="course__slug")

    class Meta:
        model = Feedback
        fields = ["source", "course"]


class AdminFeedbackFilter(filters.FilterSet):
    source = filters.ChoiceFilter(choices=Feedback.Source.choices)
    status = filters.ChoiceFilter(choices=Feedback.Status.choices)
    course_id = filters.NumberFilter(field_name="course_id")
    rating = filters.NumberFilter()
    is_featured = filters.BooleanFilter()

    class Meta:
        model = Feedback
        fields = ["source", "status", "course_id", "rating", "is_featured"]
