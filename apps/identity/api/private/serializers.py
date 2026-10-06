from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.core.api.fields import EmailField, PhoneField
from apps.identity import services
from apps.identity.api.serializers import UserWriteSerializer
from apps.identity.models import User
from apps.profiles.api.serializers import AdminStudentProfileSerializer


class UserOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "phone", "email"]


class AdminUserSerializer(UserWriteSerializer):
    """The roster; what a teacher may change is decided by `CanManageUsers`."""

    phone = PhoneField(max_length=20, validators=[UniqueValidator(queryset=User.objects.all())])
    name = serializers.CharField(max_length=150)
    email = EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[UniqueValidator(queryset=User.objects.all(), lookup="iexact")],
    )
    role = serializers.ChoiceField(choices=User.Role.choices, required=False)
    student = AdminStudentProfileSerializer(required=False, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "role",
            "student",
            "image",
            "password",
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is None:
            # No OTP on this path, so a new account needs a password to sign in.
            fields["password"].required = True
            fields["password"].allow_blank = False
        return fields

    def create(self, validated_data):
        return services.create_account(validated_data)

    def update(self, instance, validated_data):
        return services.update_account(instance, validated_data)
