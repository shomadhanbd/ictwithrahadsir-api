"""Assembles the app's two audiences into one namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:billing:orders')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'billing'

urlpatterns = [
    path('public/', include('apps.billing.api.public.urls')),
    path('private/', include('apps.billing.api.private.urls')),
]
