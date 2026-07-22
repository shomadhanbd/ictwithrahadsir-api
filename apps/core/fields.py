import hashlib

from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers


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
