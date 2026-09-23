from rest_framework import serializers


class UploadUrlRequestSerializer(serializers.Serializer):
    """Body of `POST /aws-upload-url`: the desired object key.

    Leading slashes are stripped so the key cannot escape the bucket root
    or, on the local backend, resolve to an absolute path.
    """

    name = serializers.CharField(max_length=255)

    def validate_name(self, value):
        name = value.lstrip('/').strip()
        if not name:
            raise serializers.ValidationError('`name` is required.')
        if '..' in name.split('/'):
            raise serializers.ValidationError('`name` may not traverse directories.')
        return name


class SmsBalanceResponseSerializer(serializers.Serializer):
    balance = serializers.IntegerField()
    currency = serializers.CharField()


class UploadUrlResponseSerializer(serializers.Serializer):
    """Where to PUT the bytes, and the key to submit afterwards.

    Identical whether the storage backend is S3 or the local stand-in, so a
    caller never needs to know which is active.
    """

    url = serializers.CharField()
    key = serializers.CharField()
