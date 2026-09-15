from django.contrib import admin

from apps.academic.models import Batch, ClassLevel, Group, Subject


@admin.register(ClassLevel)
class ClassLevelAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'slug', 'group_count', 'subject_count',
        'question_count', 'chapter_count', 'is_active', 'order',
    )
    list_editable = (
        'group_count', 'subject_count', 'question_count', 'chapter_count', 'is_active', 'order',
    )
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'slug', 'subject_count', 'question_count', 'chapter_count', 'is_active', 'order',
    )
    list_editable = ('subject_count', 'question_count', 'chapter_count', 'is_active', 'order')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'class_level', 'group', 'slug', 'question_count', 'chapter_count', 'is_active', 'order',
    )
    list_editable = ('question_count', 'chapter_count', 'is_active', 'order')
    list_filter = ('class_level', 'group', 'is_active')
    search_fields = ('name', 'slug')
    autocomplete_fields = ('class_level', 'group')
    #: Not prepopulated: the slug carries the level and group too, which only
    #: `Subject.save()` can assemble.
    readonly_fields = ('slug',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('class_level', 'group')


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'class_level', 'slug', 'is_active', 'order')
    list_editable = ('is_active', 'order')
    list_filter = ('class_level', 'is_active')
    search_fields = ('name', 'slug')
    autocomplete_fields = ('class_level',)
    readonly_fields = ('slug',)

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('class_level')
