"""Assembles the app's two audiences into one namespace.

The prefixes live here and the route names in the two sibling modules, so
`reverse('api:assessment:exam_detail')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'assessment'

urlpatterns = [
    path('public/', include('apps.assessment.api.public.urls')),
    path('private/', include('apps.assessment.api.private.urls')),
]
