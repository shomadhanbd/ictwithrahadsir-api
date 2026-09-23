"""Admin CRUD for the academic taxonomy.

Generic `APIView`s rather than a router, matching `apps.identity`. Every class
declares `permission_classes`: the project default is `IsAuthenticatedOrReadOnly`,
so one that leaves it off is world-readable.
"""

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
from apps.core.api.permissions import IsFullAdminOrTeacherReadOnly

#: The names are Bangla; an admin searches for "hsc".
SLUG_SEARCH = ["name", "slug"]


class AdminClassLevelListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.all()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminClassLevelDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.all()


class AdminGroupListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer
    queryset = Group.objects.all()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminGroupDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = GroupSerializer
    queryset = Group.objects.all()


class AdminSubjectListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.select_related("class_level", "group")
    search_fields = ["name", "slug", "class_level__name", "group__name"]
    filterset_fields = ["class_level", "group", "is_active"]


class AdminSubjectDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.select_related("class_level", "group")


class AdminChapterListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.select_related("subject")
    search_fields = ["name", "slug", "subject__name"]
    filterset_fields = ["subject", "is_locked", "is_active"]


class AdminChapterDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = ChapterSerializer
    queryset = Chapter.objects.select_related("subject")


class AdminTopicListCreateAPIView(ListCreateAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = TopicSerializer
    queryset = Topic.objects.select_related("chapter")
    search_fields = ["name", "slug", "chapter__name"]
    filterset_fields = ["chapter", "is_active"]


class AdminTopicDetailAPIView(RetrieveUpdateDestroyAPIView):
    permission_classes = [IsFullAdminOrTeacherReadOnly]
    serializer_class = TopicSerializer
    queryset = Topic.objects.select_related("chapter")


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
