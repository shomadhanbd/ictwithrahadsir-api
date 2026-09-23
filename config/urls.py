"""Root URLconf.

The API is served under `/api/`, split by audience: `/api/private/` is the
back-office panel, `/api/public/` is the client app. The prefix names *which
frontend* calls a route, not whether it needs a token -- `public/me/` and
`public/orders/` both require one.

Resources are named for the domain rather than for the Django app that
happens to own them, so `notices` can move out of `content` without breaking
a client.

Deliberately unversioned: both consumers ship from this repo, so a breaking
change is a coordinated deploy rather than a second URL tree to keep alive.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Each app's api/urls.py carries its own namespace and assembles its
# private/public halves, so routes reverse as `api:<app>:<route_name>`.
api_patterns = (
    [
        path('', include('apps.core.api.urls')),
        path('', include('apps.academic.api.urls')),
        path('', include('apps.question.api.urls')),
        path('', include('apps.profiles.api.urls')),
        path('', include('apps.identity.api.urls')),
        path('', include('apps.courses.api.urls')),
        path('', include('apps.exam.api.urls')),
        path('', include('apps.billing.api.urls')),
        path('', include('apps.content.api.urls')),
    ],
    'api',
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_patterns)),
    # Generated from the serializers, so it cannot drift from the code the
    # way a hand-written document would. Deliberately outside the `api`
    # namespace above: these are documentation, not endpoints a client calls.
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
