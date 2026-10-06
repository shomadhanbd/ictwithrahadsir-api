from django.contrib import admin

from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet, QuestionSource


class QuestionSetInline(admin.StackedInline):
    model = QuestionSet
    can_delete = False
    extra = 0


class QuestionOptionInline(admin.TabularInline):
    model = QuestionOption
    extra = 4


@admin.register(QuestionSource)
class QuestionSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'year', 'unit', 'is_active')
    list_editable = ('is_active',)
    list_filter = ('kind', 'is_active', 'year')
    search_fields = ('name', 'unit')


@admin.register(QuestionBlock)
class QuestionBlockAdmin(admin.ModelAdmin):
    list_display = ('id', 'kind', 'subject', 'chapter', 'order_in_chapter', 'question_count', 'is_active')
    list_editable = ('order_in_chapter', 'is_active')
    list_filter = ('kind', 'is_active', 'subject')
    search_fields = ('sources__name',)
    autocomplete_fields = ('subject', 'chapter')
    filter_horizontal = ('topics', 'sources')
    readonly_fields = ('question_count',)
    inlines = (QuestionSetInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subject', 'chapter')


@admin.register(QuestionSet)
class QuestionSetAdmin(admin.ModelAdmin):
    list_display = ('id', 'block', 'stimulus_type')
    list_filter = ('stimulus_type',)
    search_fields = ('stimulus_content',)


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'question_type', 'label', 'marks', 'order_in_set', 'block', 'question_set')
    list_filter = ('question_type',)
    search_fields = ('prompt_content',)
    raw_id_fields = ('block', 'question_set')
    inlines = (QuestionOptionInline,)
