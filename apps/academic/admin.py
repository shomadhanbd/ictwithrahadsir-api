from django.contrib import admin

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic


@admin.register(ClassLevel)
class ClassLevelAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'question_count',
        'is_active',
        'order',
    )
    list_editable = ('is_active', 'order')
    readonly_fields = ('question_count',)
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'slug',
        'question_count',
        'is_active',
        'order',
    )
    list_editable = ('is_active', 'order')
    readonly_fields = ('question_count',)
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'class_level',
        'group',
        'slug',
        'question_count',
        'is_active',
        'order',
    )
    list_editable = ('is_active', 'order')
    readonly_fields = ('question_count',)
    list_filter = ('class_level', 'group', 'is_active')
    search_fields = ('name', 'slug')
    autocomplete_fields = ('class_level', 'group')

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('class_level', 'group')


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = (
        'chapter_number',
        'name',
        'subject',
        'slug',
        'question_count',
        'practice_enabled',
        'is_active',
    )
    list_editable = ('practice_enabled', 'is_active')
    readonly_fields = ('question_count',)
    list_filter = ('subject', 'practice_enabled', 'is_active')
    search_fields = ('name', 'slug', 'subject__name')
    autocomplete_fields = ('subject',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('subject')


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'chapter', 'slug', 'question_count', 'is_active')
    list_editable = ('is_active',)
    readonly_fields = ('question_count',)
    list_filter = ('chapter', 'is_active')
    search_fields = ('name', 'slug', 'chapter__name')
    autocomplete_fields = ('chapter',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('chapter', 'chapter__subject')


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'class_level', 'slug', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    list_filter = ('class_level', 'is_active')
    search_fields = ('name', 'slug')
    autocomplete_fields = ('class_level',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('class_level')
