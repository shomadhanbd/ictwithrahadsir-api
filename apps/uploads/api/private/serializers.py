from rest_framework import serializers

from apps.uploads.validators import KINDS


class UploadRequestSerializer(serializers.Serializer):
    file = serializers.FileField()
    kind = serializers.ChoiceField(choices=sorted(KINDS))

    def validate(self, attrs):
        attrs["extension"] = KINDS[attrs["kind"]](attrs["file"])
        return attrs


class UploadResponseSerializer(serializers.Serializer):
    link = serializers.URLField()
