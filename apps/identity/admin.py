"""Users and one-time codes."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.admin import ReadOnlyAdmin

from .models import OTP, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ('-date_joined',)
    list_display = ('id', 'name', 'phone', 'email', 'role', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('role', 'is_staff', 'is_active', 'date_joined')
    # Phone first: it is the USERNAME_FIELD and what a student quotes.
    search_fields = ('phone', 'name', 'email', 'institution')
    date_hierarchy = 'date_joined'
    readonly_fields = ('date_joined', 'last_login', 'email_verified_at', 'phone_verified_at')
    fieldsets = (
        (None, {'fields': ('phone', 'email', 'password')}),
        (
            'Profile',
            {
                'fields': (
                    'name',
                    'guardian_phone',
                    'institution',
                    'educational_session',
                    'role',
                    'image',
                )
            },
        ),
        (
            'Permissions',
            {
                'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
                'description': (
                    'Role drives the API. `admin` and `instructor` both reach '
                    '/api/v1/admin/*; `is_staff` additionally grants access to this site.'
                ),
            },
        ),
        (
            'Verification',
            {
                'classes': ('collapse',),
                'fields': ('email_verified_at', 'phone_verified_at', 'last_login', 'date_joined'),
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                'classes': ('wide',),
                'fields': ('phone', 'email', 'name', 'password1', 'password2', 'role'),
            },
        ),
    )
    filter_horizontal = ('groups', 'user_permissions')


@admin.register(OTP)
class OTPAdmin(ReadOnlyAdmin):
    """Read-only, and the code itself is masked.

    Anyone who can read a live code for a phone number can complete
    `/auth/otp/verify` for it and take the account over -- these are login
    credentials, not diagnostics. The columns that are actually useful when
    debugging a delivery complaint are the timings and the attempt count, and
    those are all still here.

    Codes expire on their own; `manage.py purge_expired_otps` clears the rows.
    """

    list_display = ('id', 'phone', 'masked_code', 'attempts', 'created_at', 'consumed_at')
    list_filter = ('created_at', 'consumed_at')
    search_fields = ('phone',)
    ordering = ('-created_at',)
    date_hierarchy = 'created_at'

    @admin.display(description='Code')
    def masked_code(self, otp):
        return '••••••' if otp.is_usable else 'spent'

    def has_view_permission(self, request, obj=None):
        return True
