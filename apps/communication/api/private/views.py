from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communication.api.filters import AdminNoticeFilter
from apps.communication.api.serializers import (
    AdminNoticeCategorySerializer,
    NoticeSerializer,
    SmsMessageSerializer,
    StudentSmsRequestSerializer,
)
from apps.communication.gateways import get_gateway
from apps.communication.selectors import admin_notice_categories, admin_notices, sms_to
from apps.communication.services import send_to_student
from apps.core.api.auth.permissions import IsContentStaff, IsFullAdmin
from apps.identity.models import User


class SmsBalanceAPIView(APIView):
    """`balance` is null when the gateway has none or the lookup failed."""

    permission_classes = [IsFullAdmin]

    def get(self, request):
        return Response(get_gateway().balance())


class StudentSmsAPIView(ListAPIView):
    """GET the student's SMS history; POST `{to, message}` sends one."""

    permission_classes = [IsFullAdmin]
    serializer_class = SmsMessageSerializer

    def get_student(self):
        return get_object_or_404(User.objects.select_related("student"), pk=self.kwargs["pk"])

    def get_queryset(self):
        return sms_to(self.get_student())

    def post(self, request, pk):
        body = StudentSmsRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        message = send_to_student(student=self.get_student(), sent_by=request.user, **body.validated_data)
        return Response(SmsMessageSerializer(message).data, status=status.HTTP_201_CREATED)


class AdminNoticeMixin:
    permission_classes = [IsContentStaff]
    serializer_class = NoticeSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return admin_notices()


class AdminNoticeListCreateAPIView(AdminNoticeMixin, ListCreateAPIView):
    """`?category=<id>&search=`."""

    filterset_class = AdminNoticeFilter
    search_fields = ["title", "body"]


class AdminNoticeDetailAPIView(AdminNoticeMixin, RetrieveUpdateDestroyAPIView):
    pass


class AdminNoticeCategoryMixin:
    permission_classes = [IsContentStaff]
    serializer_class = AdminNoticeCategorySerializer

    def get_queryset(self):
        return admin_notice_categories()


class AdminNoticeCategoryListCreateAPIView(AdminNoticeCategoryMixin, ListCreateAPIView):
    search_fields = ["title"]


class AdminNoticeCategoryDetailAPIView(AdminNoticeCategoryMixin, RetrieveUpdateDestroyAPIView):
    pass
