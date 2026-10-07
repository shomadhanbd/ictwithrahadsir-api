from django.urls import include, path

from apps.identity.api.public.views import (
    CurrentUserAPIView,
    OtpRequestAPIView,
    OtpVerifyAPIView,
    PasswordForgotAPIView,
    PasswordResetAPIView,
    UserLoginAPIView,
    UserLogoutAPIView,
    UserRegisterAPIView,
)

# Both frontends sign in here; the back office has no login of its own.
auth_patterns = [
    path('otp/', OtpRequestAPIView.as_view(), name='otp_request'),
    path('otp/verify/', OtpVerifyAPIView.as_view(), name='otp_verify'),
    path('register/', UserRegisterAPIView.as_view(), name='user_register'),
    path('login/', UserLoginAPIView.as_view(), name='user_login'),
    path('logout/', UserLogoutAPIView.as_view(), name='user_logout'),
    path('password/forgot/', PasswordForgotAPIView.as_view(), name='password_forgot'),
    path('password/reset/', PasswordResetAPIView.as_view(), name='password_reset'),
]

urlpatterns = [
    path('auth/', include(auth_patterns)),
    path('me/', CurrentUserAPIView.as_view(), name='current_user'),
]
