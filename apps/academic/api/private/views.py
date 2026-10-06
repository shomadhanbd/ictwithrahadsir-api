from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.academic.api.private.serializers import (
    BatchSerializer,
    ChapterSerializer,
    ClassLevelSerializer,
    GroupSerializer,
    SubjectSerializer,
    TopicSerializer,
)
from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic
from apps.core.api.auth.permissions import IsFullAdminOrTeacherReadOnly, IsTeachingStaffAdminDeletes
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


class AdminClassLevelView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.with_counts()


class AdminClassLevelListCreateAPIView(AdminClassLevelView, ListCreateAPIView):
    search_fields = ["name", "slug"]
    filterset_fields = ["is_active"]


class AdminClassLevelDetailAPIView(AdminClassLevelView, RetrieveUpdateDestroyAPIView):
    # Teachers may add a level while building the bank, but renaming or switching off one that every
    # subject, chapter and student hangs off is an admin's call.
    permission_classes = [IsFullAdminOrTeacherReadOnly]


class AdminGroupView:
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer
    queryset = Group.objects.with_counts()


class AdminGroupListCreateAPIView(AdminGroupView, ListCreateAPIView):
    search_fields = ["name", "slug"]
    filterset_fields = ["is_active"]


class AdminGroupDetailAPIView(AdminGroupView, RetrieveUpdateDestroyAPIView):
    pass


class AdminSubjectView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.with_counts().select_related("class_level", "group")


class AdminSubjectListCreateAPIView(AdminSubjectView, ListCreateAPIView):
    search_fields = ["name", "slug", "class_level__name", "group__name"]
    filterset_fields = ["class_level", "group", "is_active"]


class AdminSubjectDetailAPIView(AdminOnlyFieldsMixin, AdminSubjectView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("class_level", "group", "is_active")
    admin_only_message = "Only an admin may move a subject to another class or group, or switch it off."


class AdminChapterView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.select_related("subject")


class AdminChapterListCreateAPIView(AdminChapterView, ListCreateAPIView):
    search_fields = ["name", "slug", "subject__name"]
    filterset_fields = ["subject", "practice_enabled", "is_active"]


class AdminChapterDetailAPIView(AdminOnlyFieldsMixin, AdminChapterView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("subject",)
    admin_only_message = "Only an admin may move a chapter to another subject."


class AdminTopicView:
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = TopicSerializer
    queryset = Topic.objects.select_related("chapter")


class AdminTopicListCreateAPIView(AdminTopicView, ListCreateAPIView):
    search_fields = ["name", "slug", "chapter__name"]
    filterset_fields = ["chapter", "is_active"]


class AdminTopicDetailAPIView(AdminOnlyFieldsMixin, AdminTopicView, RetrieveUpdateDestroyAPIView):
    admin_only_fields = ("chapter",)
    admin_only_message = "Only an admin may move a topic to another chapter."


class AdminBatchView:
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = BatchSerializer
    queryset = Batch.objects.select_related("class_level")


class AdminBatchListCreateAPIView(AdminBatchView, ListCreateAPIView):
    search_fields = ["name", "slug", "class_level__name"]
    filterset_fields = ["class_level", "is_active"]


class AdminBatchDetailAPIView(AdminBatchView, RetrieveUpdateDestroyAPIView):
    pass
