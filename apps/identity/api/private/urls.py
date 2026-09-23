from django.urls import path

from apps.identity.api.private.views import (
    AdminUserDetailAPIView,
    AdminUserImportAPIView,
    AdminUserListCreateAPIView,
    AdminUserSearchAPIView,
)

#: No `app_name` -- see the note in the sibling `public/urls.py`.
# `search/` and `import/` stay above `<pk>/`, or the detail route swallows them.
urlpatterns = [
    path('users/search/', AdminUserSearchAPIView.as_view(), name='admin_user_search'),
    path('users/import/', AdminUserImportAPIView.as_view(), name='admin_user_import'),
    path('users/', AdminUserListCreateAPIView.as_view(), name='admin_user_list'),
    path('users/<int:pk>/', AdminUserDetailAPIView.as_view(), name='admin_user_detail'),
]
