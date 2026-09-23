"""The public contact form."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.support.api.serializers import ContactMessageSerializer
from apps.support.models import ContactMessage


class ContactUsAPIView(APIView):
    """GET lists the caller's own messages; POST submits a new one, which
    anonymous visitors are allowed to do.

    Note the deliberate asymmetry: GET answers `{"data": [...]}` and POST
    answers the created message bare, with no wrapper. That is inconsistent,
    and it is also the shape both frontends already parse -- the contact form
    reads the POST body directly. Normalising it would be a wire change for
    no behavioural gain, so it is documented rather than "fixed".
    """

    permission_classes = [IsAuthenticatedOrReadOnly]

    @extend_schema(
        summary="The caller's own messages",
        responses={200: OpenApiResponse(ContactMessageSerializer(many=True), description='`{data: [...]}`')},
    )
    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        qs = ContactMessage.objects.filter(user=user) if user else ContactMessage.objects.none()
        return Response({'data': ContactMessageSerializer(qs, many=True).data})

    @extend_schema(
        summary='Submit a contact message',
        request=ContactMessageSerializer,
        responses={201: ContactMessageSerializer},
    )
    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user if request.user.is_authenticated else None)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
