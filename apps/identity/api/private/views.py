from rest_framework import filters, status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response

from apps.core.api.auth.permissions import IsTeachingStaff
from apps.core.api.views.generics import UnpaginatedDataListMixin
from apps.identity import selectors
from apps.identity.api.permissions import CanManageUsers
from apps.identity.api.private.serializers import AdminUserSerializer, UserOptionSerializer
from apps.identity.services import deactivate_user

SEARCH_RESULT_LIMIT = 25


class AdminUserListCreateAPIView(ListCreateAPIView):
    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "student__institution"]
    ordering_fields = ["date_joined", "name"]

    def get_queryset(self):
        role = self.request.query_params.get("role")
        account_status = self.request.query_params.get("status")
        return selectors.roster(self.request.user, role=role, status=account_status)


class AdminUserDetailAPIView(RetrieveUpdateDestroyAPIView):
    """DELETE deactivates the account rather than deleting it."""

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        return selectors.account_detail_queryset(self.request.user)

    def destroy(self, request, *args, **kwargs):
        deactivate_user(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserSearchAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Student search for the enrolment screens; a teacher finds a new student by full phone number."""

    permission_classes = [IsTeachingStaff]
    serializer_class = UserOptionSerializer
    filter_backends = []  # `search_students` does the searching

    def get_queryset(self):
        term = self.request.query_params.get("search", "")
        return selectors.search_students(self.request.user, term, limit=SEARCH_RESULT_LIMIT)
