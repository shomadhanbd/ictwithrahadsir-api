from django.urls import include, path

app_name = 'support'

urlpatterns = [
    path('', include('apps.support.api.v1.urls')),
]
