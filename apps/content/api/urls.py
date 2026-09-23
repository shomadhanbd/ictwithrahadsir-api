"""Assembles the app's two audiences into one namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:content:home')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'content'

urlpatterns = [
    path('public/', include('apps.content.api.public.urls')),
    path('private/', include('apps.content.api.private.urls')),
]
