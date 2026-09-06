from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.core.api.fields import MediaField
from apps.core.spreadsheets import SpreadsheetField
from apps.identity.models import User
from apps.identity.phones import normalize_phone


def check_password_strength(password, field="password"):
    """Run the configured password validators, reporting failures against
    `field` rather than as non_field_errors so the client can show them on
    the input the user actually typed into."""
    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({field: list(exc.messages)})


class PhoneField(serializers.CharField):
    """A phone number, stored the one way -- see `apps.identity.phones`.

    Normalising in `to_internal_value` rather than in a `validate_phone`
    method is load-bearing: DRF runs `to_internal_value` *before* a field's
    validators, so `UniqueValidator` compares the canonical form. The other
    way round, `+8801810001111` would sail past a uniqueness check against a
    stored `01810001111` and only fail at the database, as a 500.
    """

    def to_internal_value(self, data):
        value = normalize_phone(super().to_internal_value(data))
        if not value:
            # Everything was punctuation. Blank is the honest answer, and it
            # is the message the client already knows how to show.
            self.fail("blank")
        return value


class NewPasswordSerializer(serializers.Serializer):
    """A new password, typed twice.

    Registration and password reset both ask for one, and both used to carry
    their own copy of these two fields and this check. Copies drift: one of
    them popped `password_confirmation` out of the validated data and the
    other left it in, and the reset path went years without running the
    strength validators at all, so any rule could be sidestepped by
    "forgetting" the password instead of choosing one.

    It is a base class rather than a mixin because DRF's serializer metaclass
    only collects declared fields from bases that are serializers themselves.
    """

    password = serializers.CharField(write_only=True)
    password_confirmation = serializers.CharField(write_only=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        # Confirmation first, so a typo is reported before anything more
        # expensive -- or more costly to the user, like spending an OTP.
        if attrs["password"] != attrs.pop("password_confirmation"):
            raise serializers.ValidationError(
                {"password_confirmation": ["Passwords do not match."]}
            )
        check_password_strength(attrs["password"])
        return attrs


class PasswordWriteMixin:
    """Accepting an optional plaintext `password` on a `ModelSerializer`.

    Shared by the two screens that can set somebody's password while editing
    other fields -- the admin panel's user form and the student's own profile
    page. Both need the same two things: run the configured validators when a
    password was supplied, and hash it instead of assigning it to the column.

    Assumes the concrete class declares:

        password = serializers.CharField(
            write_only=True, required=False, allow_blank=True
        )

    which stays there rather than moving here, because a plain mixin's fields
    are invisible to the serializer metaclass.
    """

    def validate_password(self, value):
        if value:
            validate_password(value)
        return value

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            # Never straight onto the column: that stores the plaintext and
            # locks the account out, since nothing would ever match it.
            instance.set_password(password)
        instance.save()
        return instance


# ---------------------------------------------------------------------------
# The user, rendered three ways
#
# One model, three audiences, three field lists -- deliberately not one
# serializer with conditional fields. `UserSerializer` is what a student sees
# of themselves, `AdminUserSerializer` is the admin panel's editable form
# (role and password are writable, which is exactly why it is separate), and
# `ProfileUpdateRequestSerializer` is the narrow subset a student may write
# to themselves. Collapsing them means one `fields` list guarded by
# `if request.user...`, which is how a student ends up able to PATCH their own
# role.
# ---------------------------------------------------------------------------


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


class AdminUserSerializer(PasswordWriteMixin, serializers.ModelSerializer):
    """Used by /admin/users CRUD -- exposes `role` as writable and accepts a
    plaintext `password` on create/update (write-only, hashed on save).

    Who is *allowed* to assign a given role, or to edit a given account, is
    not decided here: that is
    `apps.identity.api.v1.permissions.CanManageUsers`. It used to be decided
    here, and the hole that left is documented in that module.
    """

    image = MediaField(upload_to="users", required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    # Declared rather than generated, so the number is canonical before
    # `UniqueValidator` runs. The validator has to be restated because
    # declaring the field opts out of the one ModelSerializer would have
    # built from `phone`'s `unique=True`.
    phone = PhoneField(
        max_length=20,
        required=False,
        allow_null=True,
        validators=[UniqueValidator(queryset=User.objects.all())],
    )

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
            "is_active",
            "date_joined",
        ]
        read_only_fields = ["id", "date_joined"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        # Go through the manager so phone/email normalisation, the
        # `registered_at` stamp and the unusable-password default stay in one
        # place. (`update` comes from PasswordWriteMixin.)
        return User.objects.create_user(password=password or None, **validated_data)


# ---------------------------------------------------------------------------
# What each endpoint accepts
#
# One per endpoint, on purpose: the OpenAPI schema is generated from these, so
# a declared shape is the only thing that keeps the published docs from
# drifting away from what the handler really reads. They are small because the
# work they used to do -- deciding who may act, spending an OTP -- has moved
# to the permission and service layers.
# ---------------------------------------------------------------------------


class PhoneRequestSerializer(serializers.Serializer):
    """Endpoints keyed purely on a phone number: phone-check, get-OTP,
    forgot-password."""

    phone = PhoneField(max_length=20)


class OtpVerifyRequestSerializer(PhoneRequestSerializer):
    """Shape only. Spending the code is a write, so it belongs to
    `apps.identity.services.consume_otp`, which the view calls."""

    otp = serializers.CharField(max_length=10)


class PasswordResetRequestSerializer(OtpVerifyRequestSerializer, NewPasswordSerializer):
    """A phone, the code texted to it, and the new password twice.

    Exactly the sum of its two bases, which is why it declares no fields of
    its own. What matters here is what it does *not* do: the code is not
    spent during validation. A typo in the confirmation must not cost the
    user the code they were just texted, so the view checks the account and
    calls `consume_otp` last.
    """


class UserRegisterRequestSerializer(NewPasswordSerializer):
    """Completing a profile after the phone has been OTP-verified."""

    name = serializers.CharField(max_length=150)
    phone = PhoneField(max_length=20)
    #: `institute` on the wire, `institution` on the model. The existing web
    #: form sends the former and is not being changed for this.
    institute = serializers.CharField(
        source="institution", max_length=255, required=False, allow_blank=True
    )
    educational_session = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )


class UserImportRequestSerializer(serializers.Serializer):
    file = SpreadsheetField()


class UserLoginRequestSerializer(serializers.Serializer):
    phone = PhoneField(required=False)
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


class ProfileUpdateRequestSerializer(PasswordWriteMixin, serializers.ModelSerializer):
    """What a student may change about themselves from `/me/`.

    The field list is the security boundary: `role`, `is_active` and `phone`
    are absent, so no amount of extra keys in the request body can reach them.
    """

    image = MediaField(upload_to="users", required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "name",
            "guardian_phone",
            "institution",
            "educational_session",
            "image",
            "password",
        ]


# ---------------------------------------------------------------------------
# Response serializers
#
# The auth endpoints answer with small ad-hoc payloads rather than a resource.
# Declaring them keeps the key names -- and their order, which both frontends
# destructure -- in one readable place instead of inside the handlers.
# ---------------------------------------------------------------------------


class PhoneCheckResponseSerializer(serializers.Serializer):
    exists = serializers.BooleanField()


class OtpRequestResponseSerializer(serializers.Serializer):
    """What `/auth/otp` reports back.

    The client calls this on *every* login attempt, so it must not start
    failing once a code has been sent: within the cooldown it still answers
    200 with the account state and simply does not send a second SMS.
    `resend_in` is the seconds remaining before another code may be asked
    for, and is 0 when one was just sent.
    """

    user_exist = serializers.BooleanField()
    password_exist = serializers.BooleanField()
    message = serializers.CharField()
    resend_in = serializers.IntegerField()


class AuthTokenResponseSerializer(serializers.Serializer):
    """`{token, user}` -- what login, register and OTP-verify all return.

    `user` is null on the OTP-verify step for a number with no account yet:
    the row exists so the token has an owner, but there is no profile to
    show until `/auth/register` fills one in.
    """

    token = serializers.CharField()
    user = UserSerializer(allow_null=True)


class PasswordResetResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    message = serializers.CharField()
