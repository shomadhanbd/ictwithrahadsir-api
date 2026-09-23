from django.urls import include, path

from apps.identity.api.public.views import (
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

#: Signing in is one endpoint for both frontends -- the back-office has no
#: login of its own -- so auth lives here, with the audience that owns the
#: majority of these routes.
auth_patterns = [
    path('login/', UserLoginAPIView.as_view(), name='user_login'),
    path('register/', UserRegisterAPIView.as_view(), name='user_register'),
    path('logout/', UserLogoutAPIView.as_view(), name='user_logout'),
    path('phone-check/', PhoneCheckAPIView.as_view(), name='phone_check'),
    path('otp/', OtpRequestAPIView.as_view(), name='otp_request'),
    path('otp/verify/', OtpVerifyAPIView.as_view(), name='otp_verify'),
    path('password/forgot/', PasswordForgotAPIView.as_view(), name='password_forgot'),
    path('password/reset/', PasswordResetAPIView.as_view(), name='password_reset'),
]

#: No `app_name`: assembled into the app's single namespace by
#: `apps.identity.api.urls`, so route names survive the split.
urlpatterns = [
    path('auth/', include(auth_patterns)),
    path('me/', CurrentUserAPIView.as_view(), name='current_user'),
]
