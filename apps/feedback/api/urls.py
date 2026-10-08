from django.urls import include, path

app_name = "feedback"

urlpatterns = [
    path("public/", include("apps.feedback.api.public.urls")),
    path("private/", include("apps.feedback.api.private.urls")),
]
