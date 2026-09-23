from django.db.models import Q

from rest_framework import filters, status
from rest_framework.generics import (
    ListAPIView,
    ListCreateAPIView,
    RetrieveUpdateDestroyAPIView,
)
from rest_framework.response import Response

from apps.core.api.permissions import IsTeachingStaff
from apps.core.api.viewsets import UnpaginatedDataListMixin
from apps.identity.api.permissions import CanManageUsers
from apps.identity.api.serializers import (
    AdminUserSerializer,
    UserOptionSerializer,
)
from apps.identity.models import User
from apps.identity.services import (
    deactivate_user,
)


class AdminUserListCreateAPIView(ListCreateAPIView):
    """GET /admin/users/ -- the paginated roster. POST -- create an account."""

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "student__institution"]
    ordering_fields = ["date_joined", "name"]

    #: The `?role=` / `?status=` value meaning "do not filter on this".
    ANY = "all"

    def get_queryset(self):
        # Both are followed for every row of the page.
        users = User.objects.registered().prefetch_related("groups").select_related("student")
        role = self.request.query_params.get("role")
        status_filter = self.request.query_params.get("status")

        if role and role != self.ANY:
            users = users.filter(groups__name=role)

        if status_filter == "inactive":
            users = users.filter(is_active=False)
        elif status_filter != self.ANY:
            users = users.filter(is_active=True)
        return users


class AdminUserDetailAPIView(RetrieveUpdateDestroyAPIView):
    """GET/PUT/PATCH/DELETE /admin/users/<pk>/. DELETE deactivates."""

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    queryset = User.objects.prefetch_related("groups").select_related("student")

    def destroy(self, request, *args, **kwargs):
        deactivate_user(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserSearchAPIView(UnpaginatedDataListMixin, ListAPIView):
    """GET /admin/users/search/ -- typeahead for the enrolment screens."""

    permission_classes = [IsTeachingStaff]
    serializer_class = UserOptionSerializer
    RESULT_LIMIT = 25

    def get_queryset(self):
        students = User.objects.students().filter(is_active=True)
        search = self.request.query_params.get("search", "")
        if search:
            students = students.filter(
                Q(name__icontains=search) | Q(phone__icontains=search) | Q(email__icontains=search)
            )
        return students[: self.RESULT_LIMIT]

    def get_list_payload(self, request, *args, **kwargs):
        return self.get_serializer(self.get_queryset(), many=True).data
