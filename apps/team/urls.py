from rest_framework.routers import DefaultRouter

from django.urls import path

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("admin/team", views.AdminTeamViewSet, basename="admin-team")

urlpatterns = [
    path("admin/teacher", views.admin_teacher_lookup),
] + router.urls
