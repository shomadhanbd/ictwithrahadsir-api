from django.urls import path

from apps.support.api.private.views import (
    AdminContactDetailAPIView,
    AdminContactListAPIView,
    AdminContactToggleReadAPIView,
)

#: No `app_name` -- see the note in the sibling `public/urls.py`.
urlpatterns = [
    path('contact-messages/', AdminContactListAPIView.as_view(), name='admin_contact_list'),
    # Marking as read acts on the message, so the id leads and the action follows.
    path(
        'contact-messages/<int:pk>/read/',
        AdminContactToggleReadAPIView.as_view(),
        name='admin_contact_toggle_read',
    ),
    path(
        'contact-messages/<int:pk>/',
        AdminContactDetailAPIView.as_view(),
        name='admin_contact_detail',
    ),
]
