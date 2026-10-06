from django.urls import include, path

app_name = 'content'

urlpatterns = [
    path('public/', include('apps.content.api.public.urls')),
    path('private/', include('apps.content.api.private.urls')),
]
