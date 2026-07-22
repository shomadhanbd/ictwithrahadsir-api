"""
Implements the `/aws-upload-url` presigned-upload contract the admin panel
already speaks: POST a desired object key, get back a URL; PUT the raw file
bytes to that URL; then submit that same URL string as the field's value.

With USE_S3=True this really is an S3/DigitalOcean-Spaces presigned PUT URL
(bucket configured public-read, so the stored URL keeps working for GET
afterwards). With USE_S3=False (default) it points at `local_media_upload`
below, a self-contained endpoint that accepts the signed PUT and serves the
file back out on GET from the same URL -- so the contract is identical
either way and callers never need to know which backend is active.
"""

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

SIGNING_SALT = "core.media-upload"
SIGNING_MAX_AGE = 15 * 60  # 15 minutes to complete the PUT


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_upload_url(request):
    """POST /aws-upload-url  body: {name: "<folder>/<filename>"}"""
    name = request.data.get("name")
    if not name:
        return Response({"message": "`name` is required."}, status=422)
    name = name.lstrip("/")

    if settings.USE_S3:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                "Key": name,
                "ACL": "public-read",
            },
            ExpiresIn=SIGNING_MAX_AGE,
        )
        return Response({"url": url, "key": name})

    token = signing.dumps(name, salt=SIGNING_SALT)
    path = f"/api/media-upload/{name}"
    url = request.build_absolute_uri(f"{path}?token={token}")
    return Response({"url": url, "key": name})


@csrf_exempt
def local_media_upload(request, name):
    """PUT: writes the raw request body to storage at `name` (signed-token
    verified). GET: streams the stored file back out. Deliberately a plain
    Django view (not DRF) since the PUT body is a raw file, not a DRF-parsed
    payload, and the caller sends no Authorization header (mirrors how a
    presigned S3 PUT URL works -- auth is baked into the token itself)."""

    if request.method == "PUT":
        token = request.GET.get("token", "")
        try:
            verified_name = signing.loads(token, salt=SIGNING_SALT, max_age=SIGNING_MAX_AGE)
        except signing.BadSignature:
            return HttpResponseForbidden("Invalid or expired upload token.")
        if verified_name != name:
            return HttpResponseForbidden("Token does not match upload path.")

        if default_storage.exists(name):
            default_storage.delete(name)
        default_storage.save(name, ContentFile(request.body))
        return HttpResponse(status=204)

    if request.method == "GET":
        if not default_storage.exists(name):
            return HttpResponseNotFound()
        return FileResponse(default_storage.open(name, "rb"))

    return HttpResponse(status=405)
