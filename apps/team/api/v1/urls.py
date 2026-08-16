from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.team.api.v1.views import AdminTeacherLookupAPIView, AdminTeamViewSet

app_name = 'v1'

router = SimpleRouter(trailing_slash=False)
router.register('admin/team', AdminTeamViewSet, basename='admin-team')

urlpatterns = [
    path('admin/teacher', AdminTeacherLookupAPIView.as_view(), name='admin_teacher_lookup'),
] + router.urls
