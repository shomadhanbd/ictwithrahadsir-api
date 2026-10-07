from django.contrib.auth import password_validation

from rest_framework import serializers

from apps.core.api.serializers.fields import MediaField


class UserWriteSerializer(serializers.ModelSerializer):
    """What the admin user form and the user's own profile form share."""

    image = MediaField(required=False)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    def validate_password(self, value):
        if value:
            password_validation.validate_password(value, self.instance)
        return value
