from django.urls import path

from apps.support.api.public.views import ContactUsAPIView

#: No `app_name`: these are assembled into the app's single `v1` namespace by
#: `apps.support.api.urls`, so route names are unchanged by the split.
urlpatterns = [
    # `contact-us` was the name of a page; this is a collection of messages.
    path('contact-messages/', ContactUsAPIView.as_view(), name='contact_messages'),
]
