from rest_framework.generics import GenericAPIView

CLIENT_HINT_HEADERS = {"platform": "X-Platform", "app_version": "X-App-Version"}


class SerializerAPIView(GenericAPIView):
    """An action endpoint: no queryset, but a declared `serializer_class`."""

    def validated_data(self, request, *, from_query=False):
        source = request.query_params if from_query else request.data
        serializer = self.get_serializer(data=source)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


def request_meta(request) -> dict:
    """Client hints sent with a request, kept for debugging only."""
    hints = {key: request.headers.get(header) for key, header in CLIENT_HINT_HEADERS.items()}
    return {key: value for key, value in hints.items() if value}
