from django.urls import include, path

app_name = 'dashboard'

urlpatterns = [
    path('private/', include('apps.dashboard.api.private.urls')),
]
