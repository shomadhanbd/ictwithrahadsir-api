from django.urls import include, path

app_name = 'content'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.content.api.v1.urls')),
]
