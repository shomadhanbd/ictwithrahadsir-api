from django.urls import include, path

app_name = 'accounts'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them. Adopting the blueprint's /api/accounts/v1/ scheme
    # later means changing this prefix and the matching one in config/urls.py.
    path('', include('apps.accounts.api.v1.urls')),
]
