import copy

from django import forms
from django.contrib import admin

from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.exam.validators import validate_attempted_edit, validate_publish, validate_published_edit


class ExamAdminForm(forms.ModelForm):
    """Holds the admin site to the same publishing and locking rules as the API."""

    def clean(self):
        data = super().clean()
        exam = self.instance
        if not exam.pk:
            return data
        changed = {field: data[field] for field in self.changed_data if field in data}
        validate_attempted_edit(instance=exam, attrs=changed)
        validate_published_edit(instance=exam, attrs=changed)
        if data.get("status") == Exam.Status.PUBLISHED and exam.status != Exam.Status.PUBLISHED:
            prospective = copy.copy(exam)
            for field, value in changed.items():
                setattr(prospective, field, value)
            validate_publish(exam=prospective, sections=exam.sections.all())
        return data


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
    form = ExamAdminForm
    list_display = ('title', 'status', 'scope', 'total_marks', 'created_by')
    list_filter = ('status', 'scope')
    search_fields = ('title',)
    autocomplete_fields = ('batch',)
    readonly_fields = ('created_by', 'total_marks')
    inlines = (ExamSectionInline,)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('created_by', 'batch')


@admin.register(ExamSection)
class ExamSectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'exam', 'question_type', 'subject', 'marks', 'pass_marks', 'question_count', 'order')
    list_editable = ('order',)
    list_filter = ('question_type',)
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
