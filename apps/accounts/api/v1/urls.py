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

app_name = 'v1'

# SimpleRouter, not DefaultRouter: every app mounts its own router under the
# same /api prefix, so six DefaultRouters each registered an `api-root` view
# at /api/ and only the first-loaded one ever matched -- the index advertised
# one app's routes and hid the other five.
router = SimpleRouter(trailing_slash=False)
router.register('admin/user', AdminUserViewSet, basename='admin-user')

urlpatterns = [
    # Public / client auth
    path('check-phone', PhoneCheckAPIView.as_view(), name='phone_check'),
    path('get-otp', OtpRequestAPIView.as_view(), name='otp_request'),
    path('verify-otp', OtpVerifyAPIView.as_view(), name='otp_verify'),
    path('register', UserRegisterAPIView.as_view(), name='user_register'),
    path('login', UserLoginAPIView.as_view(), name='user_login'),
    path('forget-password', PasswordForgotAPIView.as_view(), name='password_forgot'),
    path('password-reset', PasswordResetAPIView.as_view(), name='password_reset'),
    path('logout', UserLogoutAPIView.as_view(), name='user_logout'),
    path('user', CurrentUserAPIView.as_view(), name='current_user'),
    # Admin panel
    path('admin/logout', UserLogoutAPIView.as_view(), name='admin_user_logout'),
    path('admin/user-search', AdminUserSearchAPIView.as_view(), name='admin_user_search'),
    path('admin/user/import', AdminUserImportAPIView.as_view(), name='admin_user_import'),
] + router.urls
