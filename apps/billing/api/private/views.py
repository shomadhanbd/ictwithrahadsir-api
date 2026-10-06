from django.db.models import Count, Q

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing.api.filters import AdminProductFilter
from apps.billing.api.serializers import AdminPaymentSerializer, AdminProductSerializer, CashSaleRequestSerializer
from apps.billing.models import Payment, Product
from apps.billing.services.offline import record_cash_sale
from apps.core.api.pagination import LaravelStylePageNumberPagination
from apps.core.api.permissions import IsFullAdmin, IsTeachingStaff
from apps.core.api.viewsets import AdminModelViewSet
from apps.courses.api.permissions import assert_may_manage_course


class AdminProductViewSet(AdminModelViewSet):
    """A product somebody paid for cannot be deleted (409); deactivate it."""

    serializer_class = AdminProductSerializer
    queryset = (
        Product.objects.prefetch_related('courses')
        .annotate(payment_count=Count('payments', filter=Q(payments__status=Payment.Status.VALID), distinct=True))
        .order_by('-id')
    )
    search_fields = ['title', 'product_id']
    filterset_class = AdminProductFilter


class AdminPaymentListAPIView(ListAPIView):
    permission_classes = [IsFullAdmin]
    serializer_class = AdminPaymentSerializer
    pagination_class = LaravelStylePageNumberPagination
    search_fields = ['transaction_id', 'user__name', 'user__phone']

    def get_queryset(self):
        queryset = (
            Payment.objects.select_related('user', 'product', 'recorded_by')
            .prefetch_related('product__courses')
            .order_by('-id')
        )
        value = self.request.query_params.get('status')
        return queryset.filter(status=value) if value and value != 'all' else queryset


class AdminCashSaleAPIView(APIView):
    """Records money taken at the centre for a package, and enrols the student."""

    permission_classes = [IsTeachingStaff]

    def post(self, request):
        body = CashSaleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        assert_may_manage_course(request, data["course"].pk)
        payment = record_cash_sale(
            user=data["user"],
            product=data["product"],
            amount=data["amount"],
            valid_till=data.get("valid_till"),
            recorded_by=request.user,
            note=data.get("note", ""),
        )
        return Response(AdminPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
