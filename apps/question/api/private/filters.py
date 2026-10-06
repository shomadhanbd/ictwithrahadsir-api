from django.db.models import Exists, OuterRef, Q

from django_filters import rest_framework as filters

from apps.question.models import Question, QuestionBlock, QuestionSource

PROVENANCE = {
    'source': 'sources__pk',
    'source_year': 'sources__year',
    'source_kind': 'sources__kind',
}


class QuestionBlockFilter(filters.FilterSet):
    question_type = filters.ChoiceFilter(choices=Question.Type.choices, method='by_question_type')
    no_topic = filters.BooleanFilter(method='by_no_topic')
    source = filters.NumberFilter(method='defer')
    source_year = filters.NumberFilter(method='defer')
    source_kind = filters.ChoiceFilter(choices=QuestionSource.Kind.choices, method='defer')

    class Meta:
        model = QuestionBlock
        fields = ['subject', 'chapter', 'topics', 'kind', 'is_active']

    def by_question_type(self, queryset, name, value):
        """Blocks whose questions are *all* of this type."""
        owned = Q(block=OuterRef("pk")) | Q(question_set__block=OuterRef("pk"))
        other = [choice for choice in Question.Type.values if choice != value]

        wanted = Question.objects.filter(owned, question_type=value)
        wrong = Question.objects.filter(owned, question_type__in=other)
        return queryset.filter(Exists(wanted)).filter(~Exists(wrong))

    def by_no_topic(self, queryset, name, value):
        """`EXISTS`, not a join on `topics`: a block with two topics would otherwise be listed twice."""
        tagged = Exists(QuestionBlock.topics.through.objects.filter(questionblock=OuterRef('pk')))
        return queryset.filter(~tagged if value else tagged)

    def defer(self, queryset, name, value):
        """Collected in `filter_queryset` instead, so they land in one JOIN."""
        return queryset

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)

        provenance = Q()
        for param, path in PROVENANCE.items():
            value = self.form.cleaned_data.get(param)
            if value not in (None, ''):
                provenance &= Q(**{path: value})

        if not provenance:
            return queryset
        return queryset.filter(provenance).distinct()
