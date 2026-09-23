"""The question bank, exams and attempts."""

from django.contrib import admin

from apps.core.admin import ReadOnlyAdmin, TimestampedAdmin

from .models import Exam, ExamAttempt, Question, QuestionBank


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ('question', 'answer', 'explanation')
    show_change_link = True


@admin.register(QuestionBank)
class QuestionBankAdmin(TimestampedAdmin):
    list_display = ('id', 'title', 'parent', 'order', 'question_count')
    list_editable = ('order',)
    list_filter = ('parent',)
    search_fields = ('title',)
    ordering = ('order', 'title')
    list_select_related = ('parent',)
    autocomplete_fields = ('parent',)
    inlines = [QuestionInline]

    @admin.display(description='Questions (incl. sub-folders)')
    def question_count(self, bank):
        # One query per row, and folders are few. The API path uses the
        # batched `apps.assessment.selectors.practice_banks_with_counts`.
        return bank.all_questions().count()


@admin.register(Question)
class QuestionAdmin(TimestampedAdmin):
    list_display = ('id', 'question', 'bank', 'answer')
    list_filter = ('answer', 'bank')
    search_fields = ('question', 'explanation', 'bank__title')
    ordering = ('-id',)
    list_select_related = ('bank',)
    autocomplete_fields = ('bank',)


@admin.register(Exam)
class ExamAdmin(TimestampedAdmin):
    list_display = (
        'pk',
        'content',
        'mode',
        'total_marks',
        'pass_marks',
        'duration_minutes',
        'results_published',
    )
    list_filter = ('mode', 'start_time', 'result_publish_time')
    # Needed for ExamAttempt's autocomplete on `exam`.
    search_fields = ('content__title', 'question_bank__title')
    ordering = ('-created_at',)
    list_select_related = ('content', 'question_bank')
    autocomplete_fields = ('content', 'question_bank')

    @admin.display(description='Results out', boolean=True)
    def results_published(self, exam):
        """Whether the answer key and leaderboard are visible to students.

        The single most common exam question is "why can my class not see
        their results", and the answer is nearly always this flag rather than
        anything about the exam itself.
        """
        return exam.results_published


@admin.register(ExamAttempt)
class ExamAttemptAdmin(ReadOnlyAdmin):
    """A sat paper. Read-only: marks are computed by
    `apps.assessment.services.score_paper`, and editing one by hand puts a
    student on a leaderboard they did not earn."""

    list_display = ('id', 'student', 'exam', 'marks', 'duration', 'submitted', 'created_at')
    list_filter = ('submitted', 'created_at', 'exam')
    search_fields = (
        'user__name',
        'user__phone',
        'user__email',
        'exam__content__title',
    )
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'exam', 'exam__content')

    @admin.display(description='Student', ordering='user__name')
    def student(self, attempt):
        user = attempt.user
        return f'{user.name or "-"} ({user.phone or user.email or "-"})'
