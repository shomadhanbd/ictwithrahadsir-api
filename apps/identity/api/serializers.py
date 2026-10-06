from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from apps.core.api.fields import MediaField


class UserWriteSerializer(serializers.ModelSerializer):
    image = MediaField(required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_password(self, value):
        if value:
            validate_password(value, self.instance)
        return value
