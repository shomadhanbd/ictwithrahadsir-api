from django.urls import include, path

app_name = "website"

urlpatterns = [
    path("public/", include("apps.website.api.public.urls")),
    path("private/", include("apps.website.api.private.urls")),
]
