"""The public contact form and the staff inbox behind it."""

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsAdminRole
from apps.support.api.v1.serializers import ContactMessageSerializer
from apps.support.models import ContactMessage


class ContactUsAPIView(APIView):
    """GET lists the caller's own messages; POST submits a new one, which
    anonymous visitors are allowed to do."""

    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        user = request.user if request.user.is_authenticated else None
        qs = ContactMessage.objects.filter(user=user) if user else ContactMessage.objects.none()
        return Response({'data': ContactMessageSerializer(qs, many=True).data})

    def post(self, request):
        serializer = ContactMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user if request.user.is_authenticated else None)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminContactListAPIView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = ContactMessageSerializer
    pagination_class = LaravelStylePageNumberPagination
    queryset = ContactMessage.objects.all()


class BaseAdminContactAPIView(APIView):
    permission_classes = [IsAdminRole]

    def get_message(self, pk):
        message = ContactMessage.objects.filter(pk=pk).first()
        if not message:
            raise NotFound('Message not found.')
        return message


class AdminContactToggleReadAPIView(BaseAdminContactAPIView):
    def get(self, request, pk):
        message = self.get_message(pk)
        message.is_read = True
        message.save(update_fields=['is_read'])
        return Response(ContactMessageSerializer(message).data)


class AdminContactDetailAPIView(BaseAdminContactAPIView):
    def patch(self, request, pk):
        message = self.get_message(pk)
        reply = request.data.get('reply_message')
        if reply is None:
            raise ValidationError({'reply_message': ['This field is required.']})

        message.reply_message = reply
        message.replied_by = request.user
        message.save(update_fields=['reply_message', 'replied_by'])
        return Response(ContactMessageSerializer(message).data)

    def delete(self, request, pk):
        self.get_message(pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
