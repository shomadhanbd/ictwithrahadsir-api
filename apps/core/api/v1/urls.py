from django.urls import path

from apps.core.api.v1.views import SmsBalanceAPIView, UploadUrlRequestAPIView

app_name = 'v1'

urlpatterns = [
    # `aws-upload-url` named a vendor the project does not necessarily use --
    # storage is DigitalOcean Spaces here, and the endpoint works with local
    # disk too.
    path('uploads/signed-url/', UploadUrlRequestAPIView.as_view(), name='upload_url_request'),
    # Reports on the configured SMS gateway, which is delivery plumbing
    # rather than a domain object -- so it stays in core.
    path('admin/sms-balance/', SmsBalanceAPIView.as_view(), name='sms_balance'),
]
