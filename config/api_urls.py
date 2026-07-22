from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.team.urls")),
    path("", include("apps.courses.urls")),
    path("", include("apps.exams.urls")),
    path("", include("apps.shop.urls")),
    path("", include("apps.cms.urls")),
]
