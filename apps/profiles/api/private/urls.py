from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.profiles.api.private.views import AdminTeacherLookupAPIView, AdminTeacherViewSet

router = SimpleRouter()
router.register('teachers', AdminTeacherViewSet, basename='admin-teacher')

urlpatterns = [
    # Before the router, so `lookup` is not read as a detail id.
    path('teachers/lookup/', AdminTeacherLookupAPIView.as_view(), name='admin_teacher_lookup'),
] + router.urls
