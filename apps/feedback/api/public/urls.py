from django.urls import path

from apps.feedback.api.public.views import CourseRatingAPIView, FeedbackListAPIView, MyFeedbackAPIView

urlpatterns = [
    path("feedback/", FeedbackListAPIView.as_view(), name="feedback_list"),
    path("feedback/summary/", CourseRatingAPIView.as_view(), name="course_rating"),
    path("me/feedback/general/", MyFeedbackAPIView.as_view(), name="my_general_feedback"),
    path("me/feedback/courses/<slug:slug>/", MyFeedbackAPIView.as_view(), name="my_course_feedback"),
]
