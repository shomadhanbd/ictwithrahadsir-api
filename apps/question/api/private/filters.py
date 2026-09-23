"""Query-parameter filters for the question feed.

Provenance is the reason this file exists. A block has *many* sources, so each
`.filter()` call on `sources` opens its own JOIN and the conditions are free to
match different rows: `?source=<ঢাকা বোর্ড ২০১৯>&source_year=2021` matched a
block that was in Dhaka 2019 and Rajshahi 2021, an exam that never existed.

The reference design calls this out too -- every provenance condition has to go
into one `Q` applied in a single `.filter()`, so they all describe the same
paper.
"""

from django.db.models import Exists, OuterRef, Q

from django_filters import rest_framework as filters

from apps.question.models import Question, QuestionBlock, QuestionSource

#: Query parameter -> the path it constrains on the joined `QuestionSource`.
PROVENANCE = {
    'source': 'sources__pk',
    'source_year': 'sources__year',
    'source_kind': 'sources__kind',
}


class QuestionBlockFilter(filters.FilterSet):
    #: Blocks whose questions are *all* of this type. An exam section is MCQ or
    #: CQ, so this is the first thing a teacher building one needs to narrow by,
    #: and a block has no type of its own -- it lives on its questions, which
    #: hang off either the block or its stimulus set.
    question_type = filters.ChoiceFilter(choices=Question.Type.choices, method='by_question_type')
    source = filters.NumberFilter(method='defer')
    source_year = filters.NumberFilter(method='defer')
    source_kind = filters.ChoiceFilter(choices=QuestionSource.Kind.choices, method='defer')

    class Meta:
        model = QuestionBlock
        fields = ['subject', 'chapter', 'topics', 'kind', 'is_active']

    def by_question_type(self, queryset, name, value):
        """Blocks whose questions are *all* of this type.

        "Has one" is not the rule: a stimulus with three CQ parts and one stray
        MCQ is exactly the block an MCQ section must refuse. Two `Exists`
        subqueries -- has one of this type, has none of any other -- rather
        than `.filter(...).exclude(...)`, because an `exclude` OR-ing two
        to-many paths does **not** drop such a block (measured: it came back
        under both types). `Exists` also needs no `distinct()`, since it never
        fans the join out.
        """
        owned = Q(block=OuterRef("pk")) | Q(question_set__block=OuterRef("pk"))
        other = [choice for choice in Question.Type.values if choice != value]

        wanted = Question.objects.filter(owned, question_type=value)
        wrong = Question.objects.filter(owned, question_type__in=other)
        return queryset.filter(Exists(wanted)).filter(~Exists(wrong))

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
        # One `.filter()`, so every condition describes the same source row.
        # `distinct` because a block with two matching papers would repeat.
        return queryset.filter(provenance).distinct()
