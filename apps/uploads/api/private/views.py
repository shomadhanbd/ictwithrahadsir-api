from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsStaffMember
from apps.uploads.api.private.serializers import UploadRequestSerializer, UploadResponseSerializer
from apps.uploads.links import public_link
from apps.uploads.services import save_upload


class UploadAPIView(APIView):
    """Stores an image or PDF and returns its link, which the caller then saves on whatever needs it."""

    permission_classes = [IsStaffMember]
    parser_classes = [MultiPartParser]

    def post(self, request):
        serializer = UploadRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        name = save_upload(data["file"], kind=data["kind"], extension=data["extension"])
        link = public_link(name)
        return Response(UploadResponseSerializer({"link": link}).data, status=status.HTTP_201_CREATED)
