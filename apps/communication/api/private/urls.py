from django.urls import path

from apps.communication.api.private.views import (
    AdminNoticeCategoryDetailAPIView,
    AdminNoticeCategoryListCreateAPIView,
    AdminNoticeDetailAPIView,
    AdminNoticeListCreateAPIView,
    SmsBalanceAPIView,
    StudentSmsAPIView,
)

urlpatterns = [
    path("sms-balance/", SmsBalanceAPIView.as_view(), name="sms_balance"),
    path("users/<int:pk>/sms/", StudentSmsAPIView.as_view(), name="student_sms"),
    path("notices/", AdminNoticeListCreateAPIView.as_view(), name="admin_notice_list"),
    path("notices/<slug:slug>/", AdminNoticeDetailAPIView.as_view(), name="admin_notice_detail"),
    path("notice-categories/", AdminNoticeCategoryListCreateAPIView.as_view(), name="admin_notice_category_list"),
    path(
        "notice-categories/<int:pk>/",
        AdminNoticeCategoryDetailAPIView.as_view(),
        name="admin_notice_category_detail",
    ),
]
