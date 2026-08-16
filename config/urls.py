"""Root URLconf.

The API is served twice on purpose:

  /api/v1/...  canonical -- versioned, resource-oriented, trailing slashes
  /api/...     deprecated -- the original flat paths, unchanged

Both hit the same views. The aliases exist so the backend can deploy ahead
of the clients, and so anything still calling the old paths (a bookmarked
link, an integration we do not know about) keeps working. Delete
`apps/*/api/legacy_urls.py` and the mount below once traffic there is zero.

Resources are named for the domain rather than for the Django app that
happens to own them, so `notices` can move out of `cms` without breaking a
client.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core.api.v1.views import LocalMediaUploadView

# Canonical. Each app's api/urls.py carries its own namespace and includes
# its versioned module, so routes reverse as `api:<app>:v1:<route_name>`.
api_v1_patterns = (
    [
        path('', include('apps.core.api.urls')),
        path('', include('apps.accounts.api.urls')),
        path('', include('apps.team.api.urls')),
        path('', include('apps.courses.api.urls')),
        path('', include('apps.exams.api.urls')),
        path('', include('apps.shop.api.urls')),
        path('', include('apps.cms.api.urls')),
    ],
    'api',
)

# Deprecated aliases. No namespace and no route names -- nothing should be
# reversing these.
api_legacy_patterns = (
    [
        path('', include('apps.core.api.legacy_urls')),
        path('', include('apps.accounts.api.legacy_urls')),
        path('', include('apps.team.api.legacy_urls')),
        path('', include('apps.courses.api.legacy_urls')),
        path('', include('apps.exams.api.legacy_urls')),
        path('', include('apps.shop.api.legacy_urls')),
        path('', include('apps.cms.api.legacy_urls')),
    ],
    'legacy',
)

urlpatterns = [
    path('django-admin/', admin.site.urls),
    # Not versioned and not deprecated. This path is baked into the absolute
    # URLs already written into image/file columns across the database, so it
    # has to keep resolving for as long as those rows exist -- moving it
    # under /api/v1/ would orphan every previously uploaded file. re_path
    # because an object key may contain slashes ("<folder>/<file>.png").
    re_path(
        r'^api/media-upload/(?P<name>.+)$',
        LocalMediaUploadView.as_view(),
        name='local-media-upload',
    ),
    # v1 first so nothing in the legacy set can shadow a canonical route.
    path('api/v1/', include(api_v1_patterns)),
    path('api/', include(api_legacy_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
