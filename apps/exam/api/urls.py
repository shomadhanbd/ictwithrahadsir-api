from django.urls import include, path

app_name = 'exam'

urlpatterns = [
    path('public/', include('apps.exam.api.public.urls')),
    path('private/', include('apps.exam.api.private.urls')),
]
