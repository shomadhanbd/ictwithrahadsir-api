from django.contrib.auth import password_validation

from rest_framework import serializers

from apps.academic.models import ClassLevel, Group
from apps.core.api.serializers.fields import MediaField, PhoneField
from apps.identity import services
from apps.identity.api.serializers import UserWriteSerializer
from apps.identity.models import User
from apps.profiles.api.serializers import StudentProfileSerializer
from apps.profiles.validators import clean_student_audience

# Shared


class UserSerializer(serializers.ModelSerializer):
    image = MediaField(required=False, null_as="")
    role = serializers.CharField(read_only=True)
    student = StudentProfileSerializer(read_only=True, allow_null=True)

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
            "phone_verified_at",
            "date_joined",
        ]
        read_only_fields = ["id", "role", "phone_verified_at", "date_joined"]


class PhoneRequestSerializer(serializers.Serializer):
    phone = PhoneField(max_length=20)


class NewPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, validators=[password_validation.validate_password])
    password_confirmation = serializers.CharField(write_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["password"] != attrs.pop("password_confirmation"):
            raise serializers.ValidationError({"password_confirmation": ["Passwords do not match."]})
        return attrs


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserSerializer(allow_null=True)


# Sign up and sign in with OTP


class AccountStateResponseSerializer(serializers.Serializer):
    user_exist = serializers.BooleanField()
    password_exist = serializers.BooleanField()


class OtpRequestResponseSerializer(AccountStateResponseSerializer):
    message = serializers.CharField()
    resend_in = serializers.IntegerField()


class OtpVerifyRequestSerializer(PhoneRequestSerializer):
    otp = serializers.CharField(max_length=10)


class UserRegisterRequestSerializer(NewPasswordSerializer):
    name = serializers.CharField(max_length=150)
    phone = PhoneField(max_length=20)
    institute = serializers.CharField(source="institution", max_length=255, required=False, allow_blank=True)
    educational_session = serializers.CharField(max_length=100, required=False, allow_blank=True)
    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.active(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.active(), required=False, allow_null=True
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        verified_phone = self.context["request"].user.phone
        if attrs["phone"] != verified_phone:
            raise serializers.ValidationError({"phone": ["This number does not match the verified session."]})
        return clean_student_audience(attrs)


# Sign in with a password


class UserLoginRequestSerializer(serializers.Serializer):
    phone = PhoneField(max_length=20)
    password = serializers.CharField(write_only=True)


# Forgot password


class PasswordResetRequestSerializer(OtpVerifyRequestSerializer, NewPasswordSerializer):
    """Phone and code, plus the new password twice."""


class PasswordResetResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    message = serializers.CharField()


# The signed-in user's own profile


class ProfileUpdateRequestSerializer(UserWriteSerializer):
    student = StudentProfileSerializer(required=False, allow_null=True)
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["name", "student", "image", "password", "current_password"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # A token alone must not be enough to take the account over by setting a new password.
        changing_password = bool(attrs.get("password"))
        if changing_password and self.instance.has_usable_password():
            current_password = attrs.get("current_password") or ""
            if not self.instance.check_password(current_password):
                raise serializers.ValidationError({"current_password": ["Your current password is incorrect."]})
        return attrs

    def update(self, instance, validated_data):
        return services.update_profile(instance, validated_data)
