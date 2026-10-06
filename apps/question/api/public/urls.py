from django.urls import path

from apps.question.api.public.views import PracticeQuestionsAPIView, PracticeTreeAPIView

urlpatterns = [
    path('practice/tree/', PracticeTreeAPIView.as_view(), name='practice_tree'),
    path('practice/questions/', PracticeQuestionsAPIView.as_view(), name='practice_questions'),
]
