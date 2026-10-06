from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsFullAdmin
from apps.notifications.gateways import get_gateway


class SmsBalanceAPIView(APIView):
    """Credit left on the configured SMS gateway; `null` when there is none to ask or the lookup failed."""

    permission_classes = [IsFullAdmin]

    def get(self, request):
        return Response(get_gateway().balance())
