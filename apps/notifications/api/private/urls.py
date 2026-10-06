from django.urls import path

from apps.notifications.api.private.views import SmsBalanceAPIView

urlpatterns = [
    path('sms-balance/', SmsBalanceAPIView.as_view(), name='sms_balance'),
]
