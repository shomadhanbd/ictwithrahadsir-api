from django.urls import include, path

app_name = 'courses'

urlpatterns = [
    path('public/', include('apps.courses.api.public.urls')),
    path('private/', include('apps.courses.api.private.urls')),
]
