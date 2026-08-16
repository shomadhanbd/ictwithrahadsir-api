from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core.api.fields import MediaField

from .models import OTP, User


def check_password_strength(password, field="password"):
    """Run the configured password validators, reporting failures against
    `field` rather than as non_field_errors so the client can show them on
    the input the user actually typed into."""
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({field: list(exc.messages)})


def _is_full_admin(user) -> bool:
    return bool(
        user
        and user.is_authenticated
        and (user.is_staff or user.role == User.Role.ADMIN)
    )


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

    #: Roles that may not be handed out by a non-admin. `IsAdminRole` lets
    #: instructors reach this endpoint, so without this check an instructor
    #: could POST/PATCH `role: "admin"` and promote themselves.
    PRIVILEGED_ROLES = {User.Role.ADMIN, User.Role.INSTRUCTOR}

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

    def validate_role(self, value):
        request = self.context.get("request")
        actor = getattr(request, "user", None)
        if value in self.PRIVILEGED_ROLES and not _is_full_admin(actor):
            raise serializers.ValidationError(
                "Only an admin may assign the admin or instructor role."
            )
        return value

    def validate(self, attrs):
        # Editing somebody who already holds a privileged role is itself a
        # privileged action -- otherwise an instructor could reset an admin's
        # password and take the account over.
        if self.instance and self.instance.role in self.PRIVILEGED_ROLES:
            if not _is_full_admin(self.context.get("request").user):
                raise serializers.ValidationError(
                    {"role": ["Only an admin may modify an admin or instructor account."]}
                )
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        # Go through the manager so email normalisation and the
        # unusable-password default stay in one place.
        return User.objects.create_user(password=password or None, **validated_data)

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
        check_password_strength(attrs["password"])
        return attrs


class PhoneSerializer(serializers.Serializer):
    """Shared shape for the endpoints keyed purely on a phone number."""

    phone = serializers.CharField(max_length=20)


class VerifyOtpSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    otp = serializers.CharField(max_length=10)

    def validate(self, attrs):
        if not OTP.verify(attrs["phone"], attrs["otp"]):
            raise serializers.ValidationError({"otp": ["Invalid or expired OTP."]})
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    otp = serializers.CharField(max_length=10)
    password = serializers.CharField(write_only=True)
    password_confirmation = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Confirmation first, so a typo is reported before the OTP is burned.
        if attrs["password"] != attrs["password_confirmation"]:
            raise serializers.ValidationError(
                {"password_confirmation": ["Passwords do not match."]}
            )
        # The registration path has always run the configured password
        # validators; the reset path did not, so any password strength rule
        # could be sidestepped by "forgetting" the password.
        check_password_strength(attrs["password"])
        if not OTP.verify(attrs["phone"], attrs["otp"]):
            raise serializers.ValidationError({"otp": ["Invalid or expired OTP."]})
        return attrs


class UserImportSerializer(serializers.Serializer):
    file = serializers.FileField()

    #: Guards against a huge upload being parsed straight into memory.
    MAX_BYTES = 5 * 1024 * 1024

    def validate_file(self, value):
        if not value.name.lower().endswith((".xlsx", ".xlsm")):
            raise serializers.ValidationError("Upload an .xlsx or .xlsm workbook.")
        if value.size > self.MAX_BYTES:
            raise serializers.ValidationError("The file may not be larger than 5 MB.")
        return value


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if not attrs.get("phone") and not attrs.get("email"):
            raise serializers.ValidationError({"phone": ["Phone or email is required."]})

        if attrs.get("phone"):
            user = User.objects.filter(phone=attrs["phone"]).first()
        else:
            user = User.objects.filter(email=attrs["email"]).first()

        # One message for "no such account" and "wrong password" alike, so
        # the endpoint cannot be used to enumerate registered numbers.
        if user is None or not user.check_password(attrs["password"]):
            raise serializers.ValidationError({"password": ["Invalid credentials."]})
        if not user.is_active:
            raise serializers.ValidationError(
                {"password": ["This account has been deactivated."]}
            )

        attrs["user"] = user
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
