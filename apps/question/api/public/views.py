from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.throttling import PracticeThrottle
from apps.core.api.views import SerializerAPIView
from apps.question import selectors
from apps.question.api.public.serializers import (
    PracticeLevelSerializer,
    PracticeQueryParamsSerializer,
    PracticeQuestionSerializer,
)


class PracticeTreeAPIView(APIView):
    """Class levels → subjects → chapters that have practice questions."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"data": PracticeLevelSerializer(selectors.practice_tree(), many=True).data})


class PracticeQuestionsAPIView(SerializerAPIView):
    """A random round of MCQs with their answer keys; nothing is stored."""

    permission_classes = [AllowAny]
    throttle_classes = [PracticeThrottle]
    serializer_class = PracticeQueryParamsSerializer
    pagination_class = None
    filter_backends = []

    def get(self, request):
        params = self.validated_data(request, from_query=True)
        questions = selectors.practice_round(
            chapter_id=params["chapter"],
            topic_id=params.get("topic"),
            count=params.get("count", selectors.PRACTICE_ROUND),
        )
        return Response({"data": PracticeQuestionSerializer(questions, many=True).data})
