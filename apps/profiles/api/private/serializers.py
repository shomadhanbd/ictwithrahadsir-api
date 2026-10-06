from django.contrib.auth import get_user_model

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.academic.models import ClassLevel, Subject
from apps.core.api.auth.permissions import SUPERUSER_ACCOUNT_MESSAGE, may_change_account
from apps.core.api.serializers.fields import EmailField, MediaField, PhoneField
from apps.profiles import services
from apps.profiles.api.public.serializers import TeacherSerializer
from apps.profiles.models import TeacherProfile


class AdminTeacherSerializer(TeacherSerializer):
    """Writes the teacher and their own account together."""

    user_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source="user.name", max_length=150, required=False)
    phone = PhoneField(source="user.phone", max_length=20, required=False)
    email = EmailField(source="user.email", required=False, allow_blank=True, allow_null=True)
    image = MediaField(source="user.image", required=False)
    subject_ids = serializers.PrimaryKeyRelatedField(
        source="subjects", queryset=Subject.objects.all(), many=True, required=False
    )
    level_ids = serializers.PrimaryKeyRelatedField(
        source="levels", queryset=ClassLevel.objects.all(), many=True, required=False
    )
    can_sign_in = serializers.BooleanField(source="user.can_sign_in", read_only=True)

    class Meta(TeacherSerializer.Meta):
        fields = TeacherSerializer.Meta.fields + [
            "user_id",
            "phone",
            "email",
            "experience",
            "institute",
            "subject_ids",
            "level_ids",
            "can_sign_in",
        ]

    def validate(self, attrs):
        """Editing a superuser's account is a superuser's call."""
        attrs = super().validate(attrs)
        if not may_change_account(self.context["request"].user, getattr(self.instance, "user", None)):
            raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        if self.instance is None:
            account = attrs.get("user", {})
            errors = {}
            if not account.get("name"):
                errors["name"] = "A name is required to create the account."
            if not account.get("phone"):
                errors["phone"] = "A phone number is required to create the account."
            if errors:
                raise serializers.ValidationError(errors)
        return attrs

    def validate_phone(self, value):
        """Checked here so a number already in use is a field error, not a database error."""
        if value and self._other_accounts().filter(phone=value).exists():
            raise serializers.ValidationError("Another account already uses this phone number.")
        return value

    def validate_email(self, value):
        """Checked here so an address already in use is a field error, not a database error."""
        if value and self._other_accounts().filter(email__iexact=value).exists():
            raise serializers.ValidationError("Another account already uses this email.")
        return value

    def create(self, validated_data):
        return services.create_teacher(validated_data)

    def update(self, instance, validated_data):
        return services.update_teacher(instance, validated_data)

    def _other_accounts(self):
        """Every account but the one this teacher already has."""
        return get_user_model().objects.exclude(pk=getattr(self.instance, "user_id", None))


class AdminTeacherOptionSerializer(serializers.ModelSerializer):
    """One choice in the "assign a teacher to a course" picker."""

    user_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source="user.name", read_only=True)

    class Meta:
        model = TeacherProfile
        fields = ["id", "user_id", "name", "designation"]
