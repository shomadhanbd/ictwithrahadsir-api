from django.urls import include, path

app_name = "materials"

urlpatterns = [
    path("public/", include("apps.materials.api.public.urls")),
    path("private/", include("apps.materials.api.private.urls")),
]
