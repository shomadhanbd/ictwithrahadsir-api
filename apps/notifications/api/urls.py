from django.urls import include, path

app_name = 'notifications'

urlpatterns = [
    path('private/', include('apps.notifications.api.private.urls')),
]
