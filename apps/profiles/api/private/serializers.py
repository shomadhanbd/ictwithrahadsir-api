from django.contrib.auth import get_user_model
from django.db import transaction

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.academic.models import ClassLevel, Group, Subject
from apps.core.api.fields import MediaField, PhoneField
from apps.profiles.models import GuardianProfile, StudentProfile, TeacherProfile
from apps.profiles.services import ensure_teacher_role

# -- students ----------------------------------------------------------------


class StudentProfileSerializer(serializers.ModelSerializer):
    """The nested `student` block on every user payload.

    `guardian_name` and `guardian_phone` are flattened out of `GuardianProfile`:
    both frontends read them at this level and `/me` is a frozen contract, so
    splitting the model must not split the payload.
    """

    #: `default=""` alone is not enough: DRF's attribute walk turns a missing
    #: reverse `OneToOne` into `None` before the default is consulted, and these
    #: were blank-able string columns before the split.
    GUARDIAN_FIELDS = ("guardian_name", "guardian_phone")

    guardian_name = serializers.CharField(source="guardian.name", required=False, allow_blank=True, default="")
    guardian_phone = PhoneField(source="guardian.phone", required=False, allow_blank=True, default="")

    class Meta:
        model = StudentProfile
        fields = ["guardian_name", "guardian_phone", "institution", "educational_session", "address"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for field in self.GUARDIAN_FIELDS:
            if data.get(field) is None:
                data[field] = ""
        return data


class AdminStudentProfileSerializer(StudentProfileSerializer):
    """The student block as the admin panel edits it: the same keys, plus where
    the student sits academically.

    Separate because the parent's key list is what `/me` and the login response
    emit, and both frontends read it.
    """

    class_level_id = serializers.PrimaryKeyRelatedField(
        source="class_level", queryset=ClassLevel.objects.all(), required=False, allow_null=True
    )
    group_id = serializers.PrimaryKeyRelatedField(
        source="group", queryset=Group.objects.all(), required=False, allow_null=True
    )

    class Meta(StudentProfileSerializer.Meta):
        fields = StudentProfileSerializer.Meta.fields + ["class_level_id", "group_id"]


class StudentProfileMixin:
    """Writes the nested `student` block. Reading needs only `allow_null`."""

    def save_student(self, user, data):
        if data is None:
            return
        # A nested `source` arrives nested: `{"guardian": {"name": ...}}`.
        guardian = data.pop("guardian", None)
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        for field, value in data.items():
            setattr(profile, field, value)
        profile.save()
        GuardianProfile.objects.update_or_create(student=profile, defaults=guardian or {})
        user.student = profile  # `select_related` cached the pre-update row


# -- teachers ----------------------------------------------------------------


class TeacherSerializer(serializers.ModelSerializer):
    """The public roster entry, shown on the homepage and course pages.

    This key list is frozen by `test_response_shapes.PUBLIC_TEACHER_KEYS`:
    both frontends read it, and the course-detail payload must stay identical
    to it.
    """

    name = serializers.CharField(source="user.name", read_only=True)
    image = MediaField(source="user.image", read_only=True)

    class Meta:
        model = TeacherProfile
        fields = ["id", "name", "designation", "description", "type", "order", "image"]


class AdminTeacherSerializer(TeacherSerializer):
    """The roster entry as the admin panel edits it.

    Writes the account and the profile together, so adding a teacher stays one
    screen. `user_id` links an existing account; without it one is created from
    `name`/`phone`/`email`.
    """

    # Declared by hand, so DRF does not attach the OneToOne's own validator --
    # without this a duplicate link reaches the database as an IntegrityError.
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
    #: Optional, because `user_id` alone identifies an account that already
    #: exists. Required only when one is being created -- see `_resolve_user`.
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
    #: Both halves matter: a teacher seeded or imported without a password
    #: cannot sign in however active the account is, and `is_active` alone
    #: would report them as able to.
    can_sign_in = serializers.SerializerMethodField()

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

    def get_can_sign_in(self, profile) -> bool:
        user = profile.user
        # `has_usable_password()` only looks for the "!" prefix, so the empty
        # string a directly-written row carries reads as usable. Nothing can
        # authenticate against it, so check for a hash as well.
        return bool(user.is_active and user.password and user.has_usable_password())

    @transaction.atomic
    def create(self, validated_data):
        user = self._resolve_user(validated_data, instance=None)
        subjects = validated_data.pop("subjects", None)
        levels = validated_data.pop("levels", None)
        profile = TeacherProfile.objects.create(user=user, **validated_data)
        self._set_taxonomies(profile, subjects, levels)
        ensure_teacher_role(profile)
        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        user = self._resolve_user(validated_data, instance=instance)
        if user is not None:
            instance.user = user
        subjects = validated_data.pop("subjects", None)
        levels = validated_data.pop("levels", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        self._set_taxonomies(instance, subjects, levels)
        ensure_teacher_role(instance)
        return instance

    def _resolve_user(self, validated_data, instance):
        """The account this profile belongs to, created or updated as needed.

        `user_id` and the writable account fields share `source="user"`, so DRF
        hands them over merged: a model instance when only `user_id` was sent, a
        dict of account fields otherwise.
        """
        user_data = validated_data.pop("user", None)
        if user_data is None:
            return None if instance else self._require("user_id", "An account is required.")
        if not isinstance(user_data, dict):
            return user_data

        user = instance.user if instance else None
        if user is None:
            for field, message in (
                ("name", "A name is required to create the account."),
                ("phone", "A phone number is required to create the account."),
            ):
                if not user_data.get(field):
                    self._require(field, message)
            return get_user_model().objects.create_user(**user_data)
        for field, value in user_data.items():
            setattr(user, field, value)
        user.save()
        return user

    @staticmethod
    def _set_taxonomies(profile, subjects, levels):
        if subjects is not None:
            profile.subjects.set(subjects)
        if levels is not None:
            profile.levels.set(levels)

    @staticmethod
    def _require(field, message):
        raise serializers.ValidationError({field: [message]})
