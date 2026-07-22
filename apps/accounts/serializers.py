from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.core.fields import MediaField

from .models import User


class UserSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="users", required=False)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "guardian_phone",
            "institution",
            "educational_session",
            "device_id",
            "fcm_token",
            "role",
            "image",
            "email_verified_at",
            "phone_verified_at",
            "date_joined",
        ]
        read_only_fields = ["id", "role", "email_verified_at", "phone_verified_at", "date_joined"]


class AdminUserSerializer(serializers.ModelSerializer):
    """Used by /admin/user CRUD -- exposes `role` as writable and accepts a
    plaintext `password` on create/update (write-only, hashed on save)."""

    image = MediaField(upload_to="users", required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "email",
            "phone",
            "guardian_phone",
            "institution",
            "educational_session",
            "role",
            "image",
            "password",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    institute = serializers.CharField(source="institution", max_length=255, required=False, allow_blank=True)
    educational_session = serializers.CharField(max_length=100, required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)
    password_confirmation = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirmation"):
            raise serializers.ValidationError(
                {"password_confirmation": ["Passwords do not match."]}
            )
        validate_password(attrs["password"])
        return attrs


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get("phone") and not attrs.get("email"):
            raise serializers.ValidationError({"phone": ["Phone or email is required."]})
        return attrs


class ProfileUpdateSerializer(serializers.ModelSerializer):
    image = MediaField(upload_to="users", required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ["name", "guardian_phone", "institution", "educational_session", "image", "password"]

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
