from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.auth.permissions import IsFullAdmin, IsTeachingStaff
from apps.dashboard import selectors
from apps.dashboard.api.private.serializers import (
    DashboardSummarySerializer,
    PaymentChartSerializer,
    SalesOverviewSerializer,
)


class DashboardSummaryAPIView(APIView):
    permission_classes = [IsTeachingStaff]

    def get(self, request):
        return Response(DashboardSummarySerializer(selectors.dashboard_summary(request.user)).data)


class SalesOverviewAPIView(APIView):
    permission_classes = [IsFullAdmin]

    def get(self, request):
        return Response(SalesOverviewSerializer(selectors.sales_overview()).data)


class PaymentChartAPIView(APIView):
    permission_classes = [IsFullAdmin]

    def get(self, request):
        return Response(PaymentChartSerializer(selectors.payment_chart()).data)
