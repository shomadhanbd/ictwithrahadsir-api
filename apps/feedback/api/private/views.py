from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView

from apps.core.api.auth.permissions import IsContentStaff
from apps.feedback.api.filters import AdminFeedbackFilter
from apps.feedback.api.serializers import AdminFeedbackSerializer
from apps.feedback.selectors import admin_feedback


class AdminFeedbackMixin:
    permission_classes = [IsContentStaff]
    serializer_class = AdminFeedbackSerializer

    def get_queryset(self):
        return admin_feedback()


class AdminFeedbackListCreateAPIView(AdminFeedbackMixin, ListCreateAPIView):
    """`?source=&status=&course_id=&rating=&is_featured=&search=`; POST adds feedback received elsewhere."""

    filterset_class = AdminFeedbackFilter
    search_fields = ["name", "designation", "comment", "course__title"]


class AdminFeedbackDetailAPIView(AdminFeedbackMixin, RetrieveUpdateDestroyAPIView):
    pass
