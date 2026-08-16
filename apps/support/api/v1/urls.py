from django.urls import path

from apps.support.api.v1.views import (
    AdminContactDetailAPIView,
    AdminContactListAPIView,
    AdminContactToggleReadAPIView,
    ContactUsAPIView,
)

app_name = 'v1'

urlpatterns = [
    # `contact-us` was the name of a page; this is a collection of messages.
    path('contact-messages/', ContactUsAPIView.as_view(), name='contact_messages'),
    path('admin/contact-messages/', AdminContactListAPIView.as_view(), name='admin_contact_list'),
    # Marking as read acts on the message, so the id leads and the action
    # follows.
    path(
        'admin/contact-messages/<int:pk>/read/',
        AdminContactToggleReadAPIView.as_view(),
        name='admin_contact_toggle_read',
    ),
    path(
        'admin/contact-messages/<int:pk>/',
        AdminContactDetailAPIView.as_view(),
        name='admin_contact_detail',
    ),
]
