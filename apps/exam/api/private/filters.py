from django.db.models import Q

from django_filters import rest_framework as filters

from apps.exam.models import Exam
from apps.question.models import Question

SECTION_SCOPE = {
    'subject': 'sections__subject_id',
    'class_level': 'sections__subject__class_level_id',
    'question_type': 'sections__question_type',
}


class ExamFilter(filters.FilterSet):
    course = filters.NumberFilter(field_name='lesson__course_id')
    subject = filters.NumberFilter(method='defer')
    class_level = filters.NumberFilter(method='defer')
    question_type = filters.ChoiceFilter(choices=Question.Type.choices, method='defer')

    class Meta:
        model = Exam
        fields = ['status', 'scope', 'batch', 'created_by', 'course']

    def defer(self, queryset, name, value):
        """Collected in `filter_queryset` instead, so they land in one JOIN."""
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        scope = Q()
        for param, path in SECTION_SCOPE.items():
            value = self.form.cleaned_data.get(param)
            if value not in (None, ''):
                scope &= Q(**{path: value})

        if not scope:
            return queryset
        return queryset.filter(scope).distinct()
