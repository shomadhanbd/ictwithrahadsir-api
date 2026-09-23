"""Pieces of the identity API that both audiences build on."""

from rest_framework.generics import (
    GenericAPIView,
)


class SerializerAPIView(GenericAPIView):
    """An action endpoint: no queryset, but a declared `serializer_class`."""

    def validated_data(self, request, *, from_query=False):
        source = request.query_params if from_query else request.data
        serializer = self.get_serializer(data=source)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data
