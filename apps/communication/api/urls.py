from django.urls import include, path

app_name = "communication"

urlpatterns = [
    path("public/", include("apps.communication.api.public.urls")),
    path("private/", include("apps.communication.api.private.urls")),
]
