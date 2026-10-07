from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.admin import ReadOnlyAdmin
from apps.identity.models import OTP, User
from apps.identity.roles import may_change_account
from apps.profiles.models import StudentProfile, TeacherProfile


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    extra = 0
    verbose_name_plural = 'Student Profile'


class TeacherProfileInline(admin.StackedInline):
    model = TeacherProfile
    extra = 0
    verbose_name_plural = 'Teacher Profile'
    filter_horizontal = ('subjects', 'levels')


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    # The list
    list_display = ('id', 'name', 'phone', 'email', 'role', 'is_active', 'date_joined')
    list_filter = ('groups', 'is_active', 'date_joined')
    search_fields = ('phone', 'name', 'email', 'student__institution')
    ordering = ('-date_joined',)
    date_hierarchy = 'date_joined'

    # The edit form
    fieldsets = (
        (None, {'fields': ('phone', 'email', 'password')}),
        ('Profile', {'fields': ('name', 'image')}),
        (
            'Permissions',
            {
                'fields': ('is_active', 'is_superuser', 'groups', 'user_permissions'),
                'description': (
                    'Role is group membership: put the account in exactly one of '
                    '<code>admin</code>, <code>moderator</code>, <code>teacher</code> or '
                    '<code>student</code>. There is no <code>is_staff</code> to set — access '
                    'to this site follows from the role, or from <code>is_superuser</code>.'
                ),
            },
        ),
        ('Dates', {'classes': ('collapse',), 'fields': ('phone_verified_at', 'last_login', 'date_joined')}),
    )
    readonly_fields = ('phone_verified_at', 'last_login', 'date_joined')
    filter_horizontal = ('groups', 'user_permissions')
    inlines = (StudentProfileInline, TeacherProfileInline)

    # The add form
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('phone', 'email', 'name', 'password1', 'password2', 'groups')}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('groups')

    def get_readonly_fields(self, request, obj=None):
        """Only a superuser grants superuser or loose permissions; an admin's group already holds every permission."""
        fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return fields
        return (*fields, 'is_superuser', 'user_permissions')

    def has_change_permission(self, request, obj=None):
        return may_change_account(request.user, obj) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return may_change_account(request.user, obj) and super().has_delete_permission(request, obj)

    @admin.display(description='Role')
    def role(self, user):
        return user.role or '--'


@admin.register(OTP)
class OTPAdmin(ReadOnlyAdmin):
    list_display = ('id', 'phone', 'purpose', 'masked_code', 'attempts', 'created_at', 'consumed_at')
    list_filter = ('purpose', 'created_at', 'consumed_at')
    search_fields = ('phone',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Code')
    def masked_code(self, otp):
        return '••••••' if otp.is_usable else 'used or expired'
