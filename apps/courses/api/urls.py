from django.urls import include, path

app_name = 'courses'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.courses.api.v1.urls')),
]
