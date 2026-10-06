from django.contrib.auth import get_user_model

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.validators import UniqueValidator

from apps.academic.models import ClassLevel, Subject
from apps.core.api.fields import MediaField, PhoneField
from apps.core.api.permissions import SUPERUSER_ACCOUNT_MESSAGE, may_change_account
from apps.profiles import services
from apps.profiles.api.public.serializers import TeacherSerializer
from apps.profiles.models import TeacherProfile


class AdminTeacherSerializer(TeacherSerializer):
    """Writes the account and the profile together; `user_id` links an existing account."""

    # Declared by hand so a duplicate link fails validation instead of hitting the database.
    user_id = serializers.PrimaryKeyRelatedField(
        source="user",
        queryset=get_user_model()._default_manager.all(),
        required=False,
        allow_null=True,
        validators=[
            UniqueValidator(
                queryset=TeacherProfile.objects.all(),
                message="That account is already linked to another teacher.",
            )
        ],
        help_text="The account this teacher signs in with.",
    )
    name = serializers.CharField(source="user.name", max_length=150, required=False)
    phone = PhoneField(source="user.phone", max_length=20, required=False)
    email = serializers.EmailField(source="user.email", required=False, allow_blank=True, allow_null=True)
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
        """Linking a superuser, or editing a linked one's account, would be a back door into it."""
        attrs = super().validate(attrs)
        actor = self.context["request"].user
        for account in (attrs.get("user"), getattr(self.instance, "user", None)):
            if not isinstance(account, dict) and not may_change_account(actor, account):
                raise PermissionDenied(SUPERUSER_ACCOUNT_MESSAGE)
        return attrs

    def validate_phone(self, value):
        """Checked here so a number already in use is a field error, not a database error."""
        current = getattr(self.instance, "user_id", None)
        if value and get_user_model().objects.filter(phone=value).exclude(pk=current).exists():
            raise serializers.ValidationError("Another account already uses this phone number.")
        return value

    def create(self, validated_data):
        return services.create_teacher(validated_data)

    def update(self, instance, validated_data):
        return services.update_teacher(instance, validated_data)
