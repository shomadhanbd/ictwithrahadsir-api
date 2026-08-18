from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.faculty.api.v1.views import (
    AdminInstructorViewSet,
    AdminTeacherLookupAPIView,
    AdminTeamViewSet,
)

app_name = 'v1'

router = SimpleRouter()
# `admin/team` and `admin/teacher` were two names for the same Teacher
# model; both now sit under one resource.
router.register('admin/teachers', AdminTeamViewSet, basename='admin-team')
# The per-course assignment lives with the roster it points at.
router.register('admin/instructors', AdminInstructorViewSet, basename='admin-instructor')

urlpatterns = [
    # Declared before the router so `lookup` is not read as a detail id.
    path(
        'admin/teachers/lookup/',
        AdminTeacherLookupAPIView.as_view(),
        name='admin_teacher_lookup',
    ),
] + router.urls
