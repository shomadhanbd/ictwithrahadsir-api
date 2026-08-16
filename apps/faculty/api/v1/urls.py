from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.faculty.api.v1.views import AdminTeacherLookupAPIView, AdminTeamViewSet

app_name = 'v1'

router = SimpleRouter()
# `admin/team` and `admin/teacher` were two names for the same Teacher
# model; both now sit under one resource.
router.register('admin/teachers', AdminTeamViewSet, basename='admin-team')

urlpatterns = [
    # Declared before the router so `lookup` is not read as a detail id.
    path(
        'admin/teachers/lookup/',
        AdminTeacherLookupAPIView.as_view(),
        name='admin_teacher_lookup',
    ),
] + router.urls
