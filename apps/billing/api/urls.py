from django.urls import include, path

app_name = 'billing'

urlpatterns = [
    path('public/', include('apps.billing.api.public.urls')),
    path('private/', include('apps.billing.api.private.urls')),
]
