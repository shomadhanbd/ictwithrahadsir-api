from django.urls import include, path

app_name = 'billing'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.billing.api.v1.urls')),
]
