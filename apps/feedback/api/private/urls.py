from django.urls import path

from apps.feedback.api.private.views import AdminFeedbackDetailAPIView, AdminFeedbackListCreateAPIView

urlpatterns = [
    path("feedback/", AdminFeedbackListCreateAPIView.as_view(), name="admin_feedback_list"),
    path("feedback/<int:pk>/", AdminFeedbackDetailAPIView.as_view(), name="admin_feedback_detail"),
]
