"""Assembles the app's two audiences into one `store` namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:store:product_list')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'store'

urlpatterns = [
    path('public/', include('apps.store.api.public.urls')),
    path('private/', include('apps.store.api.private.urls')),
]
