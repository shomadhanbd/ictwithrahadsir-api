from django.urls import include, path

app_name = 'identity'

urlpatterns = [
    path('public/', include('apps.identity.api.public.urls')),
    path('private/', include('apps.identity.api.private.urls')),
]
