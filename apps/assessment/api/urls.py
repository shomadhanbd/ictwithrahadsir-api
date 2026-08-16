from django.urls import include, path

app_name = 'assessment'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.assessment.api.v1.urls')),
]
