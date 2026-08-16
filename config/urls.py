"""Root URLconf.

The API is served under `/api/v1/` -- versioned, resource-oriented,
trailing slashes. The original flat paths (`/api/login`, `/api/admin/user`,
...) were carried for one release as deprecated aliases and have now been
removed; both frontends call the versioned paths.

Resources are named for the domain rather than for the Django app that
happens to own them, so `notices` can move out of `cms` without breaking a
client.

Adding v2 means copying `apps/<app>/api/v1/` to `api/v2/` and adding one
`path()` here; v1 keeps serving untouched.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from apps.core.api.v1.views import LocalMediaUploadView

# Each app's api/urls.py carries its own namespace and includes its
# versioned module, so routes reverse as `api:<app>:v1:<route_name>`.
api_v1_patterns = (
    [
        path('', include('apps.core.api.urls')),
        path('', include('apps.identity.api.urls')),
        path('', include('apps.faculty.api.urls')),
        path('', include('apps.courses.api.urls')),
        path('', include('apps.assessment.api.urls')),
        path('', include('apps.billing.api.urls')),
        path('', include('apps.content.api.urls')),
    ],
    'api',
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
    path('api/v1/', include(api_v1_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
