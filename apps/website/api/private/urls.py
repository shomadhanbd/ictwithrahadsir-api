from django.urls import path

from apps.website.api.private.views import (
    AdminBannerDetailAPIView,
    AdminBannerListCreateAPIView,
    AdminBannerMoveAPIView,
    AdminSectionDetailAPIView,
    AdminSectionListAPIView,
)

urlpatterns = [
    path("website/sections/", AdminSectionListAPIView.as_view(), name="admin_section_list"),
    path("website/sections/<str:key>/", AdminSectionDetailAPIView.as_view(), name="admin_section_detail"),
    path("website/banners/", AdminBannerListCreateAPIView.as_view(), name="admin_banner_list"),
    path("website/banners/<int:pk>/", AdminBannerDetailAPIView.as_view(), name="admin_banner_detail"),
    path("website/banners/<int:pk>/move/", AdminBannerMoveAPIView.as_view(), name="admin_banner_move"),
]
