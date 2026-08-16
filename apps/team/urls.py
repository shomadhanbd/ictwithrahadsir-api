from rest_framework.routers import SimpleRouter

from django.urls import path

from . import views

# SimpleRouter, not DefaultRouter: every app mounts its own router under
# the same /api prefix, so six DefaultRouters each registered an
# `api-root` view at /api/ and only the first-loaded one ever matched --
# the index advertised one app's routes and hid the other five. Nothing
# consumes the index or the generated `.json` suffix routes.
router = SimpleRouter(trailing_slash=False)
router.register("admin/team", views.AdminTeamViewSet, basename="admin-team")

urlpatterns = [
    path("admin/teacher", views.admin_teacher_lookup),
] + router.urls
