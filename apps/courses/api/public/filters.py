from django_filters import rest_framework as filters

from apps.courses.models import Course


class PublicCourseFilter(filters.FilterSet):
    is_online = filters.BooleanFilter()
    class_level = filters.CharFilter(field_name="class_level__slug")
    group = filters.CharFilter(field_name="group__slug")
    batch = filters.CharFilter(field_name="batch__slug")
    delivery = filters.ChoiceFilter(choices=Course.Delivery.choices)
    difficulty = filters.ChoiceFilter(choices=Course.Difficulty.choices)
    language = filters.ChoiceFilter(choices=Course.Language.choices)
    is_featured = filters.BooleanFilter()

    class Meta:
        model = Course
        fields = ["is_online", "class_level", "group", "batch", "delivery", "difficulty", "language", "is_featured"]
