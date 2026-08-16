from rest_framework.routers import SimpleRouter

from django.urls import include, path

from apps.identity.api.v1.views import (
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

router = SimpleRouter()
router.register('admin/users', AdminUserViewSet, basename='admin-user')

urlpatterns = [
    # Auth is a set of actions rather than a resource, so the verbs stay in
    # the path -- but grouped under one prefix instead of scattered across
    # the root as check-phone / get-otp / forget-password / password-reset.
    path(
        'auth/',
        include(
            [
                path('login/', UserLoginAPIView.as_view(), name='user_login'),
                path('register/', UserRegisterAPIView.as_view(), name='user_register'),
                path('logout/', UserLogoutAPIView.as_view(), name='user_logout'),
                path('phone-check/', PhoneCheckAPIView.as_view(), name='phone_check'),
                path('otp/', OtpRequestAPIView.as_view(), name='otp_request'),
                path('otp/verify/', OtpVerifyAPIView.as_view(), name='otp_verify'),
                path(
                    'password/forgot/',
                    PasswordForgotAPIView.as_view(),
                    name='password_forgot',
                ),
                path(
                    'password/reset/',
                    PasswordResetAPIView.as_view(),
                    name='password_reset',
                ),
            ]
        ),
    ),
    # The signed-in user is a singleton, not an entry in the user collection.
    path('me/', CurrentUserAPIView.as_view(), name='current_user'),
    # Admin. Declared before the router so `users/search/` and
    # `users/import/` are not swallowed by the detail route's lookup.
    path('admin/auth/logout/', UserLogoutAPIView.as_view(), name='admin_user_logout'),
    path('admin/users/search/', AdminUserSearchAPIView.as_view(), name='admin_user_search'),
    path('admin/users/import/', AdminUserImportAPIView.as_view(), name='admin_user_import'),
] + router.urls
