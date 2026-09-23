"""Assembles the app's two audiences into one `support` namespace.

The prefixes live here and the route names live in the two sibling modules,
so `reverse('api:support:admin_contact_list')` is unaffected by the split.
"""

from django.urls import include, path

app_name = 'support'

urlpatterns = [
    path('public/', include('apps.support.api.public.urls')),
    path('private/', include('apps.support.api.private.urls')),
]
