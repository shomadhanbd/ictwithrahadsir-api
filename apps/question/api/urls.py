from django.urls import include, path

app_name = 'question'

urlpatterns = [
    path('public/', include('apps.question.api.public.urls')),
    path('private/', include('apps.question.api.private.urls')),
]
