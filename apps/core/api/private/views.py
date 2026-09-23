from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsFullAdmin
from apps.core.api.private.serializers import SmsBalanceResponseSerializer
from apps.core.sms import get_sms_backend


class SmsBalanceAPIView(APIView):
    """Credit left on the configured SMS gateway; zero on the console backend."""

    permission_classes = [IsFullAdmin]

    @extend_schema(
        summary='SMS gateway balance',
        responses={200: SmsBalanceResponseSerializer},
    )
    def get(self, request):
        return Response(SmsBalanceResponseSerializer(get_sms_backend().balance()).data)
