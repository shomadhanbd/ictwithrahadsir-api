from rest_framework.routers import SimpleRouter

from django.urls import path

from . import views

# SimpleRouter, not DefaultRouter: every app mounts its own router under
# the same /api prefix, so six DefaultRouters each registered an
# `api-root` view at /api/ and only the first-loaded one ever matched --
# the index advertised one app's routes and hid the other five. Nothing
# consumes the index or the generated `.json` suffix routes.
router = SimpleRouter(trailing_slash=False)
router.register("admin/user", views.AdminUserViewSet, basename="admin-user")

urlpatterns = [
    # Public / client auth
    path("check-phone", views.CheckPhoneView.as_view()),
    path("get-otp", views.RequestOtpView.as_view()),
    path("verify-otp", views.VerifyOtpView.as_view()),
    path("register", views.RegisterView.as_view()),
    path("login", views.LoginView.as_view()),
    path("forget-password", views.ForgetPasswordView.as_view()),
    path("password-reset", views.PasswordResetView.as_view()),
    path("logout", views.LogoutView.as_view()),
    path("user", views.MeView.as_view()),
    # Admin panel
    path("admin/logout", views.LogoutView.as_view()),
    path("admin/user-search", views.AdminUserSearchView.as_view()),
    path("admin/user/import", views.AdminUserImportView.as_view()),
] + router.urls
