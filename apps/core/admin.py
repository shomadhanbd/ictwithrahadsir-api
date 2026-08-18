"""Django admin branding and the pieces every app's admin reuses.

Note this is the *Django* admin at `/django-admin/`, which is the back-office
and debugging surface. The platform's own admin panel is the Next.js app
talking to `/api/v1/admin/*`; day-to-day work happens there. What the Django
admin is for is the things that panel does not cover -- inspecting a payment
against its order, finding why a student cannot see a lesson, fixing data by
hand -- and it should be fast and searchable enough to do that under load.
"""

from django.contrib import admin

admin.site.site_header = 'Shomadhan Coaching — back office'
admin.site.site_title = 'Shomadhan Coaching'
admin.site.index_title = 'Data and diagnostics'


class TimestampedAdmin(admin.ModelAdmin):
    """Base for models inheriting `core.models.TimestampModel`.

    `created_at`/`updated_at` are `auto_now_add`/`auto_now`, so leaving them
    editable shows two fields on every form that silently ignore whatever is
    typed into them.
    """

    readonly_fields = ('created_at', 'updated_at')


class ReadOnlyAdmin(admin.ModelAdmin):
    """A model that may be inspected but never edited from here.

    For rows that are written by a flow rather than by a person -- an exam
    attempt, a completion tick, a one-time code. Editing those by hand
    produces states the application cannot otherwise reach, and the resulting
    bug is always reported as something else.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
