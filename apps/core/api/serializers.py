from rest_framework import serializers


class MergedAttrsMixin:
    """Reads a field as it will be once this request is applied."""

    def merged(self, attrs):
        def after(field, default=None):
            return attrs.get(field, getattr(self.instance, field, default))

        return after


class NonNumericSlugMixin:
    """For rows whose detail route takes an id or a slug: a slug of only digits would be read as an id, so
    it is refused here as `apps.core.slugs.unique_slug` already avoids generating one."""

    def validate_slug(self, value):
        if value and str(value).isdigit():
            raise serializers.ValidationError("A slug needs at least one letter; an all-digit slug reads as an id.")
        return value
