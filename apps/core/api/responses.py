from rest_framework import serializers


class OkResponseSerializer(serializers.Serializer):
    """`{"ok": true}`, or `{"ok": false}` when there was nothing to do."""

    ok = serializers.BooleanField()


class MessageResponseSerializer(serializers.Serializer):
    """Same shape as an error; clients tell them apart by status code."""

    message = serializers.CharField()
