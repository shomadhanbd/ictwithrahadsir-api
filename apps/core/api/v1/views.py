"""Infrastructure endpoints: the presigned-upload contract and the SMS
gateway balance.

The upload endpoints implement the flow the admin panel already speaks:
POST a desired object key, get back a URL; PUT the raw file bytes to that
URL; then submit that same URL string as the field's value.

With USE_S3=True that really is an S3/DigitalOcean-Spaces presigned PUT
URL (bucket configured public-read, so the stored URL keeps working for
GET afterwards). With USE_S3=False it points at `LocalMediaUploadView`
below, which accepts the signed PUT and serves the file back out on GET
from the same URL -- so the contract is identical either way and callers
never need to know which backend is active.
"""

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import (
    FileResponse,
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
)
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.permissions import IsAdminRole
from apps.core.api.v1.serializers import (
    SmsBalanceResponseSerializer,
    UploadUrlRequestSerializer,
    UploadUrlResponseSerializer,
)

SIGNING_SALT = 'core.media-upload'
SIGNING_MAX_AGE = 15 * 60  # 15 minutes to complete the PUT


class SmsBalanceAPIView(APIView):
    """Real SMS balance requires a live gateway account; stubbed until one
    is configured (see settings.SMS_BACKEND)."""

    permission_classes = [IsAdminRole]

    @extend_schema(
        summary='SMS gateway balance',
        responses={200: SmsBalanceResponseSerializer},
    )
    def get(self, request):
        return Response(
            SmsBalanceResponseSerializer({'balance': 0, 'currency': 'BDT'}).data
        )


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------


class UploadUrlRequestAPIView(APIView):
    """POST /aws-upload-url  body: {name: '<folder>/<filename>'}"""

    permission_classes = [IsAuthenticated]
    serializer_class = UploadUrlRequestSerializer

    @extend_schema(
        summary='Get a presigned upload URL',
        request=UploadUrlRequestSerializer,
        responses={200: UploadUrlResponseSerializer},
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data['name']

        if settings.USE_S3:
            url = self._presigned_s3_url(name)
        else:
            token = signing.dumps(name, salt=SIGNING_SALT)
            url = request.build_absolute_uri(f'/api/media-upload/{name}?token={token}')

        return Response(UploadUrlResponseSerializer({'url': url, 'key': name}).data)

    def _presigned_s3_url(self, name):
        import boto3

        client = boto3.client(
            's3',
            endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
            region_name=settings.AWS_S3_REGION_NAME,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        )
        return client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                'Key': name,
                'ACL': 'public-read',
            },
            ExpiresIn=SIGNING_MAX_AGE,
        )


@method_decorator(csrf_exempt, name='dispatch')
class LocalMediaUploadView(View):
    """PUT writes the raw request body to storage at `name` (signed-token
    verified); GET streams the stored file back out.

    Deliberately a plain Django view rather than DRF: the PUT body is raw
    file bytes, not a parseable payload, and the caller sends no
    Authorization header -- mirroring a presigned S3 PUT URL, where auth is
    baked into the token itself.
    """

    def put(self, request, name):
        token = request.GET.get('token', '')
        try:
            verified_name = signing.loads(token, salt=SIGNING_SALT, max_age=SIGNING_MAX_AGE)
        except signing.BadSignature:
            return HttpResponseForbidden('Invalid or expired upload token.')
        if verified_name != name:
            return HttpResponseForbidden('Token does not match upload path.')

        if default_storage.exists(name):
            default_storage.delete(name)
        default_storage.save(name, ContentFile(request.body))
        return HttpResponse(status=204)

    def get(self, request, name):
        if not default_storage.exists(name):
            return HttpResponseNotFound()
        return FileResponse(default_storage.open(name, 'rb'))

    def http_method_not_allowed(self, request, *args, **kwargs):
        return HttpResponseNotAllowed(['GET', 'PUT'])
