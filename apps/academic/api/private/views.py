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

SLUG_SEARCH = ["name", "slug"]  # names are Bangla; admins search slugs like "hsc"


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


class AdminClassLevelListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.with_counts()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminClassLevelDetailAPIView(RetrieveUpdateDestroyAPIView):
    # Teachers may add a level while building the bank; renaming or switching off one that every subject,
    # chapter and student hangs off is an admin's call.
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.with_counts()


class AdminGroupListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer
    queryset = Group.objects.with_counts()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminGroupDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer
    queryset = Group.objects.with_counts()


class AdminSubjectListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.with_counts().select_related("class_level", "group")
    search_fields = ["name", "slug", "class_level__name", "group__name"]
    filterset_fields = ["class_level", "group", "is_active"]


class AdminSubjectDetailAPIView(AdminOnlyFieldsMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.with_counts().select_related("class_level", "group")
    admin_only_fields = ("class_level", "group", "is_active")
    admin_only_message = "Only an admin may move a subject to another class or group, or switch it off."


class AdminChapterListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.select_related("subject")
    search_fields = ["name", "slug", "subject__name"]
    filterset_fields = ["subject", "practice_enabled", "is_active"]


class AdminChapterDetailAPIView(AdminOnlyFieldsMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.select_related("subject")
    admin_only_fields = ("subject",)
    admin_only_message = "Only an admin may move a chapter to another subject."


class AdminTopicListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = TopicSerializer
    queryset = Topic.objects.select_related("chapter")
    search_fields = ["name", "slug", "chapter__name"]
    filterset_fields = ["chapter", "is_active"]


class AdminTopicDetailAPIView(AdminOnlyFieldsMixin, RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTeachingStaffAdminDeletes]
    serializer_class = TopicSerializer
    queryset = Topic.objects.select_related("chapter")
    admin_only_fields = ("chapter",)
    admin_only_message = "Only an admin may move a topic to another chapter."


class AdminBatchListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = BatchSerializer
    queryset = Batch.objects.select_related("class_level")
    search_fields = ["name", "slug", "class_level__name"]
    filterset_fields = ["class_level", "is_active"]


class AdminBatchDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = BatchSerializer
    queryset = Batch.objects.select_related("class_level")
