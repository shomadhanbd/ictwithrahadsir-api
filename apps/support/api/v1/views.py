"""The public contact form and the staff inbox behind it."""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.support.api.v1.serializers import (
    ContactMessageSerializer,
    ContactReplyRequestSerializer,
)
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


class AdminContactListAPIView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ContactMessageSerializer
    pagination_class = LaravelStylePageNumberPagination
    # The panel's search box posts `?search=`; without these the global
    # SearchFilter matched nothing and quietly returned the whole inbox.
    search_fields = ['name', 'phone', 'subject', 'message']

    def get_queryset(self):
        # The serializer nests the sender, so the inbox is one query per
        # message without the select_related. Newest first, and explicitly
        # ordered so pagination cannot repeat or drop a message.
        qs = ContactMessage.objects.select_related('user').order_by('-id')

        # An inbox's first job is showing what has not been dealt with.
        is_read = self.request.query_params.get('is_read')
        if is_read in ('0', 'false', 'False'):
            qs = qs.filter(is_read=False)
        elif is_read in ('1', 'true', 'True'):
            qs = qs.filter(is_read=True)
        return qs


class BaseAdminContactAPIView(APIView):
    permission_classes = [IsAdminRole]

    def get_message(self, pk):
        message = ContactMessage.objects.filter(pk=pk).first()
        if not message:
            raise NotFound('Message not found.')
        return message


class AdminContactToggleReadAPIView(BaseAdminContactAPIView):
    @extend_schema(
        summary='Mark a message read',
        responses={200: ContactMessageSerializer},
    )
    def get(self, request, pk):
        message = self.get_message(pk)
        message.is_read = True
        message.save(update_fields=['is_read'])
        return Response(ContactMessageSerializer(message).data)


class AdminContactDetailAPIView(BaseAdminContactAPIView):
    @extend_schema(
        summary='Reply to a contact message',
        request=ContactReplyRequestSerializer,
        responses={200: ContactMessageSerializer},
    )
    def patch(self, request, pk):
        message = self.get_message(pk)
        serializer = ContactReplyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message.reply_message = serializer.validated_data['reply_message']
        message.replied_by = request.user
        message.save(update_fields=['reply_message', 'replied_by'])
        return Response(ContactMessageSerializer(message).data)

    @extend_schema(summary='Delete a contact message', request=None, responses={204: None})
    def delete(self, request, pk):
        self.get_message(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
