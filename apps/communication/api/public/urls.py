from django.urls import path

from apps.communication.api.public.views import (
    MyNoticesSeenAPIView,
    MyUnreadNoticesAPIView,
    PublicNoticeCategoryListAPIView,
    PublicNoticeListAPIView,
)

urlpatterns = [
    path("notices/", PublicNoticeListAPIView.as_view(), name="notice_list"),
    path("notice-categories/", PublicNoticeCategoryListAPIView.as_view(), name="notice_category_list"),
    path("me/notices/unread/", MyUnreadNoticesAPIView.as_view(), name="my_unread_notices"),
    path("me/notices/seen/", MyNoticesSeenAPIView.as_view(), name="my_notices_seen"),
]
