"""Query-parameter filters for the exam list.

`subject` and `class_level` are the reason this is a FilterSet rather than
`filterset_fields`: both reach an exam through its *many* sections, so a
separate `.filter()` per parameter opens a join each and they are free to match
different sections -- `?subject=physics&class_level=ssc` would return an exam
with an HSC Physics section and an SSC Math section, a paper that does not
exist. Same lesson, same fix as `question.filters.QuestionBlockFilter`.
"""

from django.db.models import Q

from django_filters import rest_framework as filters

from apps.exam.models import Exam
from apps.question.models import Question

#: Query parameter -> the path it constrains on the joined section.
SECTION_SCOPE = {
    'subject': 'sections__subject_id',
    'class_level': 'sections__subject__class_level_id',
    'question_type': 'sections__question_type',
}


class ExamFilter(filters.FilterSet):
    subject = filters.NumberFilter(method='defer')
    class_level = filters.NumberFilter(method='defer')
    question_type = filters.ChoiceFilter(choices=Question.Type.choices, method='defer')

    class Meta:
        model = Exam
        fields = ['status', 'scope', 'batch', 'created_by']

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
        # One `.filter()`, so every condition describes the same section.
        return queryset.filter(scope).distinct()
