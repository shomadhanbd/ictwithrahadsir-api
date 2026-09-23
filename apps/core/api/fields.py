import hashlib

from django.core.files.uploadedfile import UploadedFile

from rest_framework import serializers

from apps.core.phones import INVALID_MESSAGE, normalize_phone


class MediaField(serializers.Field):
    """
    Every image/file field on every model (Course.image, Notice.image,
    Team.image, Routine.link, Content.pdf, ...) is stored as a single
    absolute-URL string, but both frontends expect it serialized as a
    `{id, link}` object.

    Accepts writes in either shape the admin panel actually sends:
      - a real uploaded file (multipart `request.FILES`) -> saved through
        the configured storage backend (local disk or S3/Spaces).
      - a plain URL string -> already uploaded via the `/aws-upload-url`
        presigned-URL flow, stored as-is.
    """

    def __init__(self, *, upload_to="uploads", bare=False, **kwargs):
        self.upload_to = upload_to
        # A few fields (e.g. EBook.preview) are typed by the frontends as a
        # bare URL string, not the usual `{id, link}` object -- `bare=True`
        # keeps the same file-or-URL write behavior but serializes as a
        # plain string on read.
        self.bare = bare
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)
        # Describe the two shapes to the OpenAPI generator. Without this it
        # falls back to "string", which is exactly the mistake that already
        # bit the admin panel once: an interface typed these as `string`, so
        # dropping one into an `src` type-checked and then rendered the text
        # "[object Object]".
        self._spectacular_annotation = {
            "field": {"type": "string", "format": "uri", "nullable": True}
            if self.bare
            else {
                "type": "object",
                "nullable": True,
                "properties": {
                    "id": {"type": "integer"},
                    "link": {"type": "string", "format": "uri"},
                },
                "required": ["id", "link"],
            }
        }

    def to_representation(self, value):
        if not value:
            return None
        if self.bare:
            return value
        digest = hashlib.md5(value.encode()).hexdigest()[:8]
        return {"id": int(digest, 16) % 1_000_000, "link": value}

    def to_internal_value(self, data):
        if isinstance(data, UploadedFile):
            from django.core.files.storage import default_storage

            path = default_storage.save(f"{self.upload_to}/{data.name}", data)
            url = default_storage.url(path)
            request = self.context.get("request")
            if request is not None and url.startswith("/"):
                url = request.build_absolute_uri(url)
            return url
        if isinstance(data, str) and data.strip():
            return data.strip()
        raise serializers.ValidationError("Expected an uploaded file or a URL string.")


class PhoneField(serializers.CharField):
    """Accepts any spelling of a BD mobile, stores the canonical one.

    Here rather than in `identity` because `profiles` needs it for the
    guardian's number, and `profiles` must not import `identity`.
    """

    default_error_messages = {"invalid_phone": INVALID_MESSAGE}

    def to_internal_value(self, data):
        raw = super().to_internal_value(data)
        if not raw:  # only reachable with allow_blank=True
            return raw
        phone = normalize_phone(raw)
        if not phone:
            self.fail("invalid_phone")
        return phone


class EmailField(serializers.EmailField):
    def to_internal_value(self, data):
        return super().to_internal_value(data).lower()
