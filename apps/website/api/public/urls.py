from django.urls import path

from apps.website.api.public.views import HomeAPIView, LegalPageAPIView, WebsiteAPIView

urlpatterns = [
    path("website/", WebsiteAPIView.as_view(), name="website"),
    path("website/legal/<slug:slug>/", LegalPageAPIView.as_view(), name="legal_page"),
    path("home/", HomeAPIView.as_view(), name="home"),
]
