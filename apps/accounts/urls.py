from rest_framework.routers import DefaultRouter

from django.urls import path

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("admin/user", views.AdminUserViewSet, basename="admin-user")

urlpatterns = [
    # Public / client auth
    path("check-phone", views.check_phone),
    path("get-otp", views.get_otp),
    path("verify-otp", views.verify_otp),
    path("register", views.register),
    path("login", views.login_view),
    path("forget-password", views.forget_password),
    path("password-reset", views.password_reset),
    path("logout", views.LogoutView.as_view()),
    path("user", views.MeView.as_view()),
    # Admin panel
    path("admin/logout", views.LogoutView.as_view()),
    path("admin/user-search", views.user_search),
    path("admin/user/import", views.import_users),
] + router.urls
