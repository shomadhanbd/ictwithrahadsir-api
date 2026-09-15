"""Admin CRUD for the academic taxonomy.

Generic `APIView`s rather than a router, matching `apps.identity`. Every class
declares `permission_classes` explicitly: the project default is
`IsAuthenticatedOrReadOnly`, so a view that leaves it off is world-readable.
"""

from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.academic.api.v1.serializers import (
    BatchSerializer,
    ClassLevelSerializer,
    GroupSerializer,
    SubjectSerializer,
)
from apps.academic.models import Batch, ClassLevel, Group, Subject
from apps.core.api.permissions import IsFullAdmin

#: The names are Bangla; an admin searches for "hsc".
SLUG_SEARCH = ["name", "slug"]


class AdminClassLevelListCreateAPIView(ListCreateAPIView):
    """GET /admin/class-levels/ -- the education levels. POST -- add one."""

    permission_classes = [IsFullAdmin]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.all()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminClassLevelDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/class-levels/<pk>/."""

    permission_classes = [IsFullAdmin]
    serializer_class = ClassLevelSerializer
    queryset = ClassLevel.objects.all()


class AdminGroupListCreateAPIView(ListCreateAPIView):
    """GET /admin/groups/ -- the academic groups. POST -- add one."""

    permission_classes = [IsFullAdmin]
    serializer_class = GroupSerializer
    queryset = Group.objects.all()
    search_fields = SLUG_SEARCH
    filterset_fields = ["is_active"]


class AdminGroupDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/groups/<pk>/."""

    permission_classes = [IsFullAdmin]
    serializer_class = GroupSerializer
    queryset = Group.objects.all()


class AdminSubjectListCreateAPIView(ListCreateAPIView):
    """GET /admin/subjects/ -- one row per level and group. POST -- add one."""

    permission_classes = [IsFullAdmin]
    serializer_class = SubjectSerializer
    #: The payload names the level and group, so both are joined rather than
    #: fetched per row.
    queryset = Subject.objects.select_related("class_level", "group")
    search_fields = ["name", "slug", "class_level__name", "group__name"]
    #: Without these the panel cannot scope the list to one level or group --
    #: the parameter is accepted and silently ignored.
    filterset_fields = ["class_level", "group", "is_active"]


class AdminSubjectDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/subjects/<pk>/."""

    permission_classes = [IsFullAdmin]
    serializer_class = SubjectSerializer
    queryset = Subject.objects.select_related("class_level", "group")


class AdminBatchListCreateAPIView(ListCreateAPIView):
    """GET /admin/batches/ -- the cohorts. POST -- add one."""

    permission_classes = [IsFullAdmin]
    serializer_class = BatchSerializer
    queryset = Batch.objects.select_related("class_level")
    search_fields = ["name", "slug", "class_level__name"]
    filterset_fields = ["class_level", "is_active"]


class AdminBatchDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/batches/<pk>/."""

    permission_classes = [IsFullAdmin]
    serializer_class = BatchSerializer
    queryset = Batch.objects.select_related("class_level")
