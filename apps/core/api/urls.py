from django.urls import path

from apps.core.api.private.views import SmsBalanceAPIView

app_name = 'core'

urlpatterns = [
    path('private/sms-balance/', SmsBalanceAPIView.as_view(), name='sms_balance'),
]
