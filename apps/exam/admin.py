from django.contrib import admin

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion


class ExamSectionInline(admin.TabularInline):
    model = ExamSection
    extra = 0
    autocomplete_fields = ('subject',)
    readonly_fields = ('question_count', 'computed_marks')


class ExamSectionQuestionInline(admin.TabularInline):
    model = ExamSectionQuestion
    extra = 0
    raw_id_fields = ('block',)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'scope', 'total_marks', 'created_by')
    list_editable = ('status',)
    list_filter = ('status', 'scope')
    search_fields = ('title', 'slug')
    autocomplete_fields = ('batch',)
    readonly_fields = ('slug', 'created_by')
    inlines = (ExamSectionInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by', 'batch')


@admin.register(ExamSection)
class ExamSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'exam', 'question_type', 'subject', 'marks', 'pass_marks', 'question_count', 'order')
    list_editable = ('order',)
    list_filter = ('question_type',)
    # Safe to edit here now that `ExamSection.clean()` runs the same rules the
    # serializer does -- before that, every section rule was bypassable here.
    search_fields = ('title', 'exam__title')
    autocomplete_fields = ('subject',)
    raw_id_fields = ('exam',)
    readonly_fields = ('question_count', 'computed_marks')
    inlines = (ExamSectionQuestionInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('exam', 'subject')


@admin.register(ExamSectionQuestion)
class ExamSectionQuestionAdmin(admin.ModelAdmin):
    list_display = ('id', 'section', 'block', 'marks', 'order')
    list_editable = ('marks', 'order')
    search_fields = ('section__title',)
    raw_id_fields = ('section', 'block')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('section', 'block')
