"""Root URLconf.

The API lives under `/api/`, split by audience: `/api/private/` serves the
back-office panel and `/api/public/` the client app. Routes reverse as
`api:<app>:<route_name>`.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

api_patterns = (
    [
        path('', include('apps.notifications.api.urls')),
        path('', include('apps.academic.api.urls')),
        path('', include('apps.question.api.urls')),
        path('', include('apps.profiles.api.urls')),
        path('', include('apps.identity.api.urls')),
        path('', include('apps.courses.api.urls')),
        path('', include('apps.exam.api.urls')),
        path('', include('apps.billing.api.urls')),
        path('', include('apps.content.api.urls')),
        path('', include('apps.dashboard.api.urls')),
    ],
    'api',
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_patterns)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = 'apps.core.api.errors.pages.not_found'
handler500 = 'apps.core.api.errors.pages.server_failure'
