from django.urls import include, path

app_name = 'core'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them. Adopting the blueprint's /api/core/v1/ scheme later
    # means changing this prefix and the matching one in config/urls.py.
    path('', include('apps.core.api.v1.urls')),
]
