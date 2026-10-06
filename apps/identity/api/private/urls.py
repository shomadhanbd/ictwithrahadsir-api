from django.urls import path

from apps.identity.api.private.views import (
    AdminUserDetailAPIView,
    AdminUserListCreateAPIView,
    AdminUserSearchAPIView,
)

urlpatterns = [
    path('users/search/', AdminUserSearchAPIView.as_view(), name='admin_user_search'),
    path('users/', AdminUserListCreateAPIView.as_view(), name='admin_user_list'),
    path('users/<int:pk>/', AdminUserDetailAPIView.as_view(), name='admin_user_detail'),
]
