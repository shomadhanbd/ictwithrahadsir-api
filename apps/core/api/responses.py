"""Acknowledgement payloads returned by more than one app."""

from rest_framework import serializers


class OkResponseSerializer(serializers.Serializer):
    """`{"ok": true}`, or `{"ok": false}` when there was nothing to do."""

    ok = serializers.BooleanField()


class MessageResponseSerializer(serializers.Serializer):
    """`{"message": "..."}` -- the same shape as an error, so clients tell them
    apart by status code."""

    message = serializers.CharField()
