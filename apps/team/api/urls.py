from django.urls import include, path

app_name = 'team'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.team.api.v1.urls')),
]
