from django.urls import path

from apps.uploads.api.private.views import UploadAPIView

urlpatterns = [
    path('uploads/', UploadAPIView.as_view(), name='upload'),
]
