from django.urls import include, path

app_name = 'store'

urlpatterns = [
    path('', include('apps.store.api.v1.urls')),
]
