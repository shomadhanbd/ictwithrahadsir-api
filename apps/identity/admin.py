from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import OTP, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["id", "name", "phone", "email", "role", "is_staff", "date_joined"]
    list_filter = ["role", "is_staff", "is_active"]
    search_fields = ["name", "phone", "email"]
    fieldsets = (
        (None, {"fields": ("phone", "email", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "name",
                    "guardian_phone",
                    "institution",
                    "educational_session",
                    "role",
                    "image",
                )
            },
        ),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "email", "name", "password1", "password2", "role"),
            },
        ),
    )


@admin.register(OTP)
class OTPAdmin(admin.ModelAdmin):
    list_display = ["phone", "code", "created_at", "consumed_at"]
    search_fields = ["phone"]
