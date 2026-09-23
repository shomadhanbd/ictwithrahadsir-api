from django.urls import path

from rest_framework.routers import SimpleRouter

from apps.profiles.api.private.views import AdminTeacherLookupAPIView, AdminTeacherViewSet

app_name = 'profiles'

router = SimpleRouter()
router.register('private/teachers', AdminTeacherViewSet, basename='admin-teacher')

urlpatterns = [
    # Declared before the router so `lookup` is not read as a detail id.
    path(
        'private/teachers/lookup/',
        AdminTeacherLookupAPIView.as_view(),
        name='admin_teacher_lookup',
    ),
] + router.urls
