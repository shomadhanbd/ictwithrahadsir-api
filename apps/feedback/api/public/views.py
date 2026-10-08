from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.core.api.views.generics import SerializerAPIView
from apps.feedback.api.filters import FeedbackFilter
from apps.feedback.api.serializers import (
    CourseRatingQuerySerializer,
    FeedbackRequestSerializer,
    FeedbackSerializer,
    MyFeedbackSerializer,
)
from apps.feedback.selectors import course_rating, feedback_course, my_feedback, published_feedback
from apps.feedback.services import submit_feedback, withdraw_feedback


class FeedbackListAPIView(ListAPIView):
    """`?source=course|general&course=<slug>`."""

    permission_classes = [AllowAny]
    serializer_class = FeedbackSerializer
    filterset_class = FeedbackFilter

    def get_queryset(self):
        return published_feedback()


class CourseRatingAPIView(SerializerAPIView):
    """`?course=<slug>`."""

    permission_classes = [AllowAny]
    serializer_class = CourseRatingQuerySerializer

    def get(self, request):
        return Response(course_rating(self.validated_data(request, from_query=True)["course"]))


class MyFeedbackAPIView(SerializerAPIView):
    """The user's own feedback: general, or on the course in the URL. PUT writes it; it waits for approval."""

    permission_classes = [IsAuthenticated]
    serializer_class = FeedbackRequestSerializer

    def get_course(self):
        slug = self.kwargs.get("slug")
        return feedback_course(slug) if slug else None

    def get(self, request, slug=None):
        feedback = my_feedback(request.user, course=self.get_course())
        if feedback is None:
            raise NotFound("No feedback yet.")
        return Response(MyFeedbackSerializer(feedback).data)

    def put(self, request, slug=None):
        feedback = submit_feedback(user=request.user, course=self.get_course(), **self.validated_data(request))
        return Response(MyFeedbackSerializer(feedback).data)

    def delete(self, request, slug=None):
        withdraw_feedback(user=request.user, course=self.get_course())
        return Response(status=status.HTTP_204_NO_CONTENT)
