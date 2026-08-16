from django.urls import include, path

app_name = 'shop'

urlpatterns = [
    # Mounted at '' so the emitted paths stay exactly where both frontends
    # already call them.
    path('', include('apps.shop.api.v1.urls')),
]
