from rest_framework import filters, status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response

from apps.core.api.permissions import IsTeachingStaff
from apps.core.api.viewsets import UnpaginatedDataListMixin
from apps.identity import selectors
from apps.identity.api.permissions import CanManageUsers
from apps.identity.api.private.serializers import AdminUserSerializer, UserOptionSerializer
from apps.identity.services import deactivate_user


class AdminUserListCreateAPIView(ListCreateAPIView):
    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "phone", "email", "student__institution"]
    ordering_fields = ["date_joined", "name"]

    def get_queryset(self):
        params = self.request.query_params
        return selectors.roster(self.request.user, role=params.get("role"), status=params.get("status"))


class AdminUserDetailAPIView(RetrieveUpdateDestroyAPIView):
    """DELETE deactivates the account."""

    permission_classes = [CanManageUsers]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        return selectors.account_detail_queryset(self.request.user)

    def destroy(self, request, *args, **kwargs):
        deactivate_user(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserSearchAPIView(UnpaginatedDataListMixin, ListAPIView):
    """Student typeahead for the enrolment screens; a teacher finds a new student by full phone number."""

    permission_classes = [IsTeachingStaff]
    serializer_class = UserOptionSerializer
    filter_backends = []
    RESULT_LIMIT = 25

    def get_queryset(self):
        return selectors.search_students(
            self.request.user, self.request.query_params.get("search", ""), limit=self.RESULT_LIMIT
        )
