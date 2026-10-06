from django.urls import include, path

app_name = 'profiles'

urlpatterns = [
    path('private/', include('apps.profiles.api.private.urls')),
]
