"""Root URLconf.

Every app is mounted at the empty prefix so the emitted paths stay exactly
where both frontends already call them (`/api/login`, `/api/admin/user`,
...). The per-app `api/urls.py` -> `api/v1/urls.py` tiering still gives each
route a versioned reverse name such as `api:core:v1:admin_dashboard`, so
adopting the blueprint's `/api/<app>/v1/` scheme later is a matter of
changing these prefixes rather than moving code.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

api_url_patterns = (
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

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/', include(api_url_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
