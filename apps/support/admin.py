"""The staff inbox behind the public contact form."""

from django.contrib import admin, messages

from apps.core.admin import TimestampedAdmin
from apps.support.models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(TimestampedAdmin):
    list_display = ('id', 'name', 'subject', 'is_read', 'answered', 'created_at')
    list_editable = ('is_read',)
    # Unread first: an inbox's first job is showing what has not been handled.
    list_filter = ('is_read', 'created_at')
    search_fields = ('name', 'phone', 'email', 'subject', 'message')
    ordering = ('is_read', '-created_at')
    date_hierarchy = 'created_at'
    list_select_related = ('user', 'replied_by')
    autocomplete_fields = ('user', 'replied_by')
    actions = ('mark_read', 'mark_unread')

    @admin.display(description='Replied', boolean=True)
    def answered(self, message):
        return bool(message.reply_message)

    @admin.action(description='Mark selected messages as read')
    def mark_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f'{updated} message(s) marked read.', messages.SUCCESS)

    @admin.action(description='Mark selected messages as unread')
    def mark_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f'{updated} message(s) marked unread.', messages.SUCCESS)
