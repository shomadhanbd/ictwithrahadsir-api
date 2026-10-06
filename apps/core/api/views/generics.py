"""Building blocks for DRF generic views."""

from rest_framework.generics import GenericAPIView
from rest_framework.response import Response


class SerializerAPIView(GenericAPIView):
    """An action endpoint: no queryset, but a declared `serializer_class`."""

    def validated_data(self, request, *, from_query=False):
        source = request.query_params if from_query else request.data
        serializer = self.get_serializer(data=source)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class UnpaginatedDataListMixin:
    """An unpaginated list wrapped as `{"data": [...]}`."""

    pagination_class = None

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        return Response({"data": self.get_serializer(queryset, many=True).data})
