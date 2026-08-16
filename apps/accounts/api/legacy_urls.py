"""DEPRECATED flat paths, kept so clients that have not migrated to
/api/v1/ keep working. Same views as api/v1/urls.py -- add new routes
there, never here. Remove this module once traffic here is zero.
"""

from rest_framework.routers import SimpleRouter

from django.urls import path

from apps.accounts.api.v1.views import (
    AdminUserImportAPIView,
    AdminUserSearchAPIView,
    AdminUserViewSet,
    CurrentUserAPIView,
    OtpRequestAPIView,
    OtpVerifyAPIView,
    PasswordForgotAPIView,
    PasswordResetAPIView,
    PhoneCheckAPIView,
    UserLoginAPIView,
    UserLogoutAPIView,
    UserRegisterAPIView,
)


# SimpleRouter, not DefaultRouter: every app mounts its own router under the
# same /api prefix, so six DefaultRouters each registered an `api-root` view
# at /api/ and only the first-loaded one ever matched -- the index advertised
# one app's routes and hid the other five.
router = SimpleRouter(trailing_slash=False)
router.register('admin/user', AdminUserViewSet, basename='admin-user')

urlpatterns = [
    # Public / client auth
    path('check-phone', PhoneCheckAPIView.as_view()),
    path('get-otp', OtpRequestAPIView.as_view()),
    path('verify-otp', OtpVerifyAPIView.as_view()),
    path('register', UserRegisterAPIView.as_view()),
    path('login', UserLoginAPIView.as_view()),
    path('forget-password', PasswordForgotAPIView.as_view()),
    path('password-reset', PasswordResetAPIView.as_view()),
    path('logout', UserLogoutAPIView.as_view()),
    path('user', CurrentUserAPIView.as_view()),
    # Admin panel
    path('admin/logout', UserLogoutAPIView.as_view()),
    path('admin/user-search', AdminUserSearchAPIView.as_view()),
    path('admin/user/import', AdminUserImportAPIView.as_view()),
] + router.urls
