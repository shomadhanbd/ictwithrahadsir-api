"""Assembles the app's two audiences into one namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:courses:course_list')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'courses'

urlpatterns = [
    path('public/', include('apps.courses.api.public.urls')),
    path('private/', include('apps.courses.api.private.urls')),
]
