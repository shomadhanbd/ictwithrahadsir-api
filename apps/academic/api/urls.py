from django.urls import include, path

app_name = 'academic'

urlpatterns = [
    path('', include('apps.academic.api.v1.urls')),
]
