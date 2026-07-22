from rest_framework.routers import DefaultRouter

from django.urls import path

from . import views

router = DefaultRouter(trailing_slash=False)
router.register("admin/mcq-store", views.AdminMcqStoreViewSet, basename="admin-mcq-store")
router.register("admin/mcq", views.AdminMcqQuestionViewSet, basename="admin-mcq")

urlpatterns = [
    path("exams/<int:pk>", views.exam_view),
    path("ranking/<int:pk>", views.exam_ranking),
    path("admin/result", views.admin_exam_results),
] + router.urls
