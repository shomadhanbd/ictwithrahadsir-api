from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.core.api.serializers.fields import EmailField, PhoneField
from apps.identity import services
from apps.identity.api.serializers import UserWriteSerializer
from apps.identity.models import User
from apps.profiles.api.serializers import AdminStudentProfileSerializer


class AdminUserSerializer(UserWriteSerializer):
    """A user on the admin user list and form. What a teacher may change is decided by `CanManageUsers`."""

    name = serializers.CharField(max_length=150)
    email = EmailField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[UniqueValidator(queryset=User.objects.all(), lookup="iexact")],
    )
    phone = PhoneField(max_length=20, validators=[UniqueValidator(queryset=User.objects.all())])
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


class UserOptionSerializer(serializers.ModelSerializer):
    """A student in the search results of the enrolment screens."""

    class Meta:
        model = User
        fields = ["id", "name", "phone", "email"]
