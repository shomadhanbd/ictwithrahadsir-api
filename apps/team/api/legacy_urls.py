"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.team.api.v1.views import AdminTeacherLookupAPIView, AdminTeamViewSet


router = SimpleRouter(trailing_slash=False)
router.register('admin/team', AdminTeamViewSet, basename='admin-team')

urlpatterns = [
    path('admin/teacher', AdminTeacherLookupAPIView.as_view()),
] + router.urls
