from django.urls import path

from apps.content.api.public.views import (
    HomeAPIView,
    PublicPageDetailAPIView,
)

urlpatterns = [
    path('home/', HomeAPIView.as_view(), name='home'),
    path('pages/<slug:key>/', PublicPageDetailAPIView.as_view(), name='page_detail'),
]
