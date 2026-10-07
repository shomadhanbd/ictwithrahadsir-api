from django.urls import include, path

app_name = 'uploads'

urlpatterns = [
    path('private/', include('apps.uploads.api.private.urls')),
]
