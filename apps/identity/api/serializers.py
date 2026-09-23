from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.core.api.fields import EmailField, MediaField, PhoneField
from apps.core.spreadsheets import SpreadsheetField
from apps.identity.models import User
from apps.profiles.api.private.serializers import (
    AdminStudentProfileSerializer,
    StudentProfileMixin,
    StudentProfileSerializer,
)

# -- fields ------------------------------------------------------------------


class NewPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirmation = serializers.CharField(write_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["password"] != attrs.pop("password_confirmation"):
            raise serializers.ValidationError({"password_confirmation": ["Passwords do not match."]})
        return attrs


class UserWriteSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="users", required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_password(self, value):
        if value:
            validate_password(value, self.instance)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        if password:
            instance.set_password(password)
        return super().update(instance, validated_data)


# -- model serializers -------------------------------------------------------


class UserSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="users", required=False)
    role = serializers.CharField(read_only=True)
    student = StudentProfileSerializer(read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "fcm_token",
            "role",
            "student",
            "image",
            "email_verified_at",
            "phone_verified_at",
            "date_joined",
        ]
        read_only_fields = ["id", "role", "email_verified_at", "phone_verified_at", "date_joined"]


class UserOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "name", "phone", "email"]


class AdminUserSerializer(StudentProfileMixin, UserWriteSerializer):
    """The roster. What a teacher may change is decided by `CanManageUsers`."""

    #: Both required: phone is the only login identifier, and a nameless
    #: account is invisible to `UserQuerySet.registered`.
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
            # Required on create only: this path issues no OTP, so a password
            # is the account's only way in. Editing must not force a change.
            fields["password"].required = True
            fields["password"].allow_blank = False
        return fields

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        role = validated_data.pop("role", None)  # create_user defaults it
        student = validated_data.pop("student", None)
        user = User.objects.create_user(password=password, role=role, **validated_data)
        self.save_student(user, student)
        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        role = validated_data.pop("role", None)
        student = validated_data.pop("student", None)
        user = super().update(instance, validated_data)
        if role:
            user.set_role(role)
        self.save_student(user, student)
        return user


# -- request bodies ----------------------------------------------------------


class PhoneRequestSerializer(serializers.Serializer):
    phone = PhoneField(max_length=20)


class OtpVerifyRequestSerializer(PhoneRequestSerializer):
    otp = serializers.CharField(max_length=10)


class PasswordResetRequestSerializer(OtpVerifyRequestSerializer, NewPasswordSerializer):
    pass


class UserRegisterRequestSerializer(NewPasswordSerializer):
    name = serializers.CharField(max_length=150)
    phone = PhoneField(max_length=20)
    #: `institute` on the wire, unlike every other endpoint; clients send that.
    institute = serializers.CharField(source="institution", max_length=255, required=False, allow_blank=True)
    educational_session = serializers.CharField(max_length=100, required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        signed_in_as = getattr(self.context["request"].user, "phone", None)
        if attrs["phone"] != signed_in_as:
            raise serializers.ValidationError({"phone": ["This number does not match the verified session."]})
        return attrs


class UserImportRequestSerializer(serializers.Serializer):
    file = SpreadsheetField()


class UserLoginRequestSerializer(serializers.Serializer):
    phone = PhoneField()
    password = serializers.CharField(write_only=True)


class ProfileUpdateRequestSerializer(StudentProfileMixin, UserWriteSerializer):
    student = StudentProfileSerializer(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ["name", "student", "image", "password"]

    @transaction.atomic
    def update(self, instance, validated_data):
        student = validated_data.pop("student", None)
        user = super().update(instance, validated_data)
        self.save_student(user, student)
        return user


# -- response bodies ---------------------------------------------------------


class PhoneCheckResponseSerializer(serializers.Serializer):
    exists = serializers.BooleanField()


class OtpRequestResponseSerializer(serializers.Serializer):
    user_exist = serializers.BooleanField()
    password_exist = serializers.BooleanField()
    message = serializers.CharField()
    resend_in = serializers.IntegerField()


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserSerializer(allow_null=True)


class PasswordResetResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    message = serializers.CharField()
