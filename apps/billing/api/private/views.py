from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import selectors
from apps.billing.api.filters import AdminProductFilter
from apps.billing.api.serializers import (
    AdminPaymentSerializer,
    AdminProductSerializer,
    CashSaleRequestSerializer,
    SalePackageQuerySerializer,
    SalePackageSerializer,
)
from apps.billing.services.offline import record_cash_sale
from apps.core.api.auth.permissions import IsFullAdmin, IsTeachingStaff
from apps.core.api.views.generics import UnpaginatedDataListMixin
from apps.courses.api.permissions import assert_may_manage_course


class AdminProductView:
    """A product somebody paid for cannot be deleted (409); deactivate it."""

    permission_classes = [IsFullAdmin]
    serializer_class = AdminProductSerializer

    def get_queryset(self):
        return selectors.admin_products()


class AdminProductListCreateAPIView(AdminProductView, ListCreateAPIView):
    search_fields = ['title', 'product_id']
    filterset_class = AdminProductFilter


class AdminProductDetailAPIView(AdminProductView, RetrieveUpdateDestroyAPIView):
    pass


class AdminPaymentListAPIView(ListAPIView):
    permission_classes = [IsFullAdmin]
    serializer_class = AdminPaymentSerializer
    search_fields = ['transaction_id', 'user__name', 'user__phone']

    def get_queryset(self):
        return selectors.admin_payments(self.request.query_params.get('status'))


class AdminCashSaleAPIView(APIView):
    """Records money taken at the centre for a package, and enrols the student."""

    permission_classes = [IsTeachingStaff]

    def post(self, request):
        body = CashSaleRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        assert_may_manage_course(request, data["course"].pk)
        if not selectors.may_sell(request.user, data["product"]):
            raise PermissionDenied("You can only sell a package whose courses you all teach.")
        payment = record_cash_sale(
            user=data["user"],
            product=data["product"],
            amount=data["amount"],
            valid_till=data.get("valid_till"),
            recorded_by=request.user,
            note=data.get("note", ""),
        )
        return Response(AdminPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class CashSalePackageListAPIView(UnpaginatedDataListMixin, ListAPIView):
    """`?course_id=`: the packages the enrol dialog can record a cash sale against."""

    permission_classes = [IsTeachingStaff]
    serializer_class = SalePackageSerializer
    filter_backends = []

    def get_queryset(self):
        query = SalePackageQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        course = query.validated_data["course"]
        assert_may_manage_course(self.request, course.pk)
        return selectors.sale_packages(course.pk, self.request.user)
