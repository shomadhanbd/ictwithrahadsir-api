from django.urls import include, path

app_name = 'exams'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.exams.api.v1.urls')),
]
