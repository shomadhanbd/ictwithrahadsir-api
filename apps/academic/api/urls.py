from django.urls import include, path

app_name = 'academic'

urlpatterns = [
    path('public/', include('apps.academic.api.public.urls')),
    path('private/', include('apps.academic.api.private.urls')),
]
