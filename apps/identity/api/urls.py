"""Assembles the app's two audiences into one namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:identity:user_login')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'identity'

urlpatterns = [
    path('public/', include('apps.identity.api.public.urls')),
    path('private/', include('apps.identity.api.private.urls')),
]
