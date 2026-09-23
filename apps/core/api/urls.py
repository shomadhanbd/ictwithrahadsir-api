from django.urls import path

from apps.core.api.private.views import SmsBalanceAPIView, UploadUrlRequestAPIView

app_name = 'core'

urlpatterns = [
    # `aws-upload-url` named a vendor the project does not necessarily use --
    # storage is DigitalOcean Spaces here, and the endpoint works with local
    # disk too.
    path('private/uploads/signed-url/', UploadUrlRequestAPIView.as_view(), name='upload_url_request'),
    # Reports on the configured SMS gateway, which is delivery plumbing
    # rather than a domain object -- so it stays in core.
    path('private/sms-balance/', SmsBalanceAPIView.as_view(), name='sms_balance'),
]
