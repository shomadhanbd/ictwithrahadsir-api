from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.academic import selectors
from apps.academic.api.private.serializers import (
    BatchSerializer,
    ChapterSerializer,
    ClassLevelSerializer,
    GroupSerializer,
    SubjectSerializer,
    TopicSerializer,
)
from apps.core.api.auth.permissions import (
    IsFullAdminOrTeacherReadOnly,
    IsTeachingStaffAdminDeletes,
    StaffMayReadMixin,
)
from apps.identity.roles import is_full_admin


class AdminOnlyFieldsMixin:
    """Teaching staff edit the row; changing one of `admin_only_fields` (moving it under another parent,
    switching it off) restructures everything below it, so it is an admin's call."""

    admin_only_fields = ()
    admin_only_message = "Only an admin may change this."

    def perform_update(self, serializer):
        instance, data = serializer.instance, serializer.validated_data
        changed = [
            field for field in self.admin_only_fields if field in data and data[field] != getattr(instance, field)
        ]
        if changed and not is_full_admin(self.request.user):
            raise PermissionDenied(self.admin_only_message)
        super().perform_update(serializer)


# Names are Bangla, so every list also searches the slug ("hsc", "ict").


class AdminClassLevelView(StaffMayReadMixin):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ClassLevelSerializer

    def get_queryset(self):
        return selectors.admin_class_levels()


class AdminClassLevelListCreateAPIView(AdminClassLevelView, ListCreateAPIView):
    search_fields = ["name", "slug"]
    filterset_fields = ["is_active"]


class AdminClassLevelDetailAPIView(AdminClassLevelView, RetrieveUpdateDestroyAPIView):
    # Teachers may add a level while building the bank, but renaming or switching off one that every
    # subject, chapter and student hangs off is an admin's call.
    permission_classes = [IsFullAdminOrTeacherReadOnly]


class AdminGroupListAPIView(StaffMayReadMixin, ListAPIView):
    """The fixed curriculum groups, for the admin's dropdowns; they are seeded, not edited here."""

    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer

    def get_queryset(self):
        return selectors.admin_groups()

    search_fields = ["name", "slug"]
    filterset_fields = ["is_active"]


class AdminSubjectView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = SubjectSerializer

    def get_queryset(self):
        return selectors.admin_subjects()


class AdminSubjectListCreateAPIView(AdminSubjectView, ListCreateAPIView):
    search_fields = ["name", "slug", "class_level__name", "group__name"]
    filterset_fields = ["class_level", "group", "is_active"]


class AdminSubjectDetailAPIView(AdminOnlyFieldsMixin, AdminSubjectView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("class_level", "group", "is_active")
    admin_only_message = "Only an admin may move a subject to another class or group, or switch it off."


class AdminChapterView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ChapterSerializer

    def get_queryset(self):
        return selectors.admin_chapters()


class AdminChapterListCreateAPIView(AdminChapterView, ListCreateAPIView):
    search_fields = ["name", "slug", "subject__name"]
    filterset_fields = ["subject", "practice_enabled", "is_active"]


class AdminChapterDetailAPIView(AdminOnlyFieldsMixin, AdminChapterView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("subject",)
    admin_only_message = "Only an admin may move a chapter to another subject."


class AdminTopicView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = TopicSerializer

    def get_queryset(self):
        return selectors.admin_topics()


class AdminTopicListCreateAPIView(AdminTopicView, ListCreateAPIView):
    search_fields = ["name", "slug", "chapter__name"]
    filterset_fields = ["chapter", "is_active"]


class AdminTopicDetailAPIView(AdminOnlyFieldsMixin, AdminTopicView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("chapter",)
    admin_only_message = "Only an admin may move a topic to another chapter."


class AdminBatchView(StaffMayReadMixin):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = BatchSerializer

    def get_queryset(self):
        return selectors.admin_batches()


class AdminBatchListCreateAPIView(AdminBatchView, ListCreateAPIView):
    search_fields = ["name", "slug", "class_level__name"]
    filterset_fields = ["class_level", "is_active"]


class AdminBatchDetailAPIView(AdminBatchView, RetrieveUpdateDestroyAPIView):
    pass
