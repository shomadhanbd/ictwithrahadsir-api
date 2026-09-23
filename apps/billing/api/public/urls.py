from django.urls import path

from apps.billing.api.public.views import (
    FreeEnrollmentAPIView,
    OrderAPIView,
    PaymentSubmitAPIView,
)

#: No `app_name`: assembled into the app's single namespace by
#: `apps.billing.api.urls`, so route names survive the split.
urlpatterns = [
    # One collection: GET lists the caller's orders, POST places one.
    path('orders/', OrderAPIView.as_view(), name='orders'),
    path('payments/', PaymentSubmitAPIView.as_view(), name='payment_submit'),
    # Claiming a free course creates an enrolment; it is not a "purchase".
    path('enrollments/free/', FreeEnrollmentAPIView.as_view(), name='free_enrollment'),
]
