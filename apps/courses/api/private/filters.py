from django_filters import rest_framework as filters

from apps.courses.models import Content, Course, CourseTeacher, Routine, Section


def id_filterset(model, *fields):
    """A FilterSet taking each of `fields` (e.g. `course_id`) as an exact id."""
    attrs = {field: filters.NumberFilter(field_name=field) for field in fields}
    attrs["Meta"] = type("Meta", (), {"model": model, "fields": list(fields)})
    return type(f"{model.__name__}Filter", (filters.FilterSet,), attrs)


class AdminCourseFilter(filters.FilterSet):
    status = filters.ChoiceFilter(choices=Course.Status.choices)
    delivery = filters.ChoiceFilter(choices=Course.Delivery.choices)
    difficulty = filters.ChoiceFilter(choices=Course.Difficulty.choices)
    class_level_id = filters.NumberFilter(field_name="class_level_id")
    group_id = filters.NumberFilter(field_name="group_id")
    batch_id = filters.NumberFilter(field_name="batch_id")

    class Meta:
        model = Course
        fields = ["status", "delivery", "difficulty", "class_level_id", "group_id", "batch_id"]


class SectionFilter(id_filterset(Section, "course_id", "section_id")):
    """A course's list without `section_id` shows only its top-level sections."""

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        if self.data.get("course_id") and not self.data.get("section_id"):
            queryset = queryset.filter(section__isnull=True)
        return queryset


RoutineFilter = id_filterset(Routine, "course_id")
ContentFilter = id_filterset(Content, "section_id")
CourseTeacherFilter = id_filterset(CourseTeacher, "course_id")
