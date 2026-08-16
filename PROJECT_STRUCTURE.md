# Django REST API — Project Structure & Conventions

A reusable blueprint extracted from the Songify backend. Replace `songify` with your
own project package name and `config` stays as-is.

**Stack:** Django 6 · Django REST Framework 3.17 · `django-environ` · Token auth · SQLite/Postgres via `DATABASE_URL`

---

## 1. Top-level layout

```
<project-root>/
├── manage.py                  # DJANGO_SETTINGS_MODULE defaults to config.settings.local
├── .env                       # real secrets — gitignored
├── .env.example               # committed template, every key with a <placeholder>
├── .gitignore
├── db.sqlite3                 # local only
├── logs/                      # auto-created by settings; rotating debug.log
├── staticfiles/               # STATIC_ROOT, collectstatic target
├── requirements/
│   ├── base.txt               # pinned, ==, shared by all envs
│   ├── local.txt              # `-r base.txt` + dev-only tools
│   └── production.txt         # `-r base.txt` + gunicorn/psycopg etc.
├── config/                    # project config package — NEVER app code
│   ├── __init__.py
│   ├── urls.py                # root URLconf, mounts /api/ and /admin/
│   ├── wsgi.py
│   ├── asgi.py
│   └── settings/
│       ├── __init__.py        # empty
│       ├── base.py            # everything shared
│       ├── local.py           # from .base import *  → DEBUG=True, ALLOWED_HOSTS=['*']
│       └── production.py      # from .base import *  → real ALLOWED_HOSTS
└── songify/                   # ← the project package: ALL apps live inside
    ├── __init__.py
    ├── core/
    ├── identity/
    ├── billing/
    ├── payment/
    ├── music/
    └── lyrics/
```

**Rules**

- `config/` holds configuration only. No models, no views, no business logic.
- Every Django app is a subpackage of the project package, so app labels are
  registered as `'songify.<app>'` in `INSTALLED_APPS`, never bare `'<app>'`.
- `BASE_DIR = Path(__file__).resolve().parent.parent.parent` (three levels up from
  `config/settings/base.py`), and `APPS_DIR = BASE_DIR / 'songify'`.

---

## 2. App layout

Every app follows the same shape. Only create the directories the app actually needs —
`services/` and `utils/` are optional, `api/` and `migrations/` are not.

```
songify/<app>/
├── __init__.py
├── apps.py                    # <App>Config, name = 'songify.<app>'
├── models.py                  # ALL models for the app, one flat file
├── admin.py                   # ALL admin classes, one flat file
├── signals.py                 # optional; wired in apps.py ready()
├── constants.py               # optional; app-level constants
├── tests.py                   # flat file; split to tests/ only when it gets big
├── views.py                   # Django (non-API) views — usually left empty/unused
├── migrations/
│   ├── __init__.py
│   ├── 0001_initial.py
│   └── 0002_<snake_case_description>.py
├── api/                       # ← everything HTTP/DRF lives here
│   ├── __init__.py
│   ├── urls.py                # app_name = '<app>'; includes each version
│   └── v1/
│       ├── __init__.py
│       ├── urls.py            # app_name = 'v1'; the actual endpoint paths
│       ├── views.py           # APIView / GenericAPIView subclasses
│       └── serializers.py     # request + response serializers
├── services/                  # optional: third-party integrations
│   ├── __init__.py            # one-line docstring comment describing the package
│   ├── <vendor>_service.py    # one file per external provider
│   └── factory.py             # picks the provider from settings
└── utils/                     # optional: app-local helpers
    ├── __init__.py
    └── exceptions.py          # DRF APIException subclasses
```

**Why the `api/v1/` nesting:** versioning is a folder, not a URL kwarg. Adding `v2`
means copying `api/v1/` → `api/v2/` and adding one `path()` line in `api/urls.py`.
`v1` keeps working untouched.

---

## 3. URL routing — three tiers

### Tier 1 — `config/urls.py` (root)

Namespaces the whole API under `api`, then mounts each app by its URL prefix.

```python
from django.contrib import admin
from django.urls import path, include

api_url_patterns = (
    [
        path('identity/', include('songify.identity.api.urls')),
        path('billing/',  include('songify.billing.api.urls')),
        path('core/',     include('songify.core.api.urls')),
        path('payment/',  include('songify.payment.api.urls')),
        path('music/',    include('songify.music.api.urls')),
        path('lyrics/',   include('songify.lyrics.api.urls')),
    ], 'api'
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include(api_url_patterns)),
    path('api-auth/', include('rest_framework.urls')),
]
```

### Tier 2 — `songify/<app>/api/urls.py` (version dispatch)

```python
from django.urls import include, path

app_name = 'music'

urlpatterns = [
    path('v1/', include('songify.music.api.v1.urls')),
]
```

### Tier 3 — `songify/<app>/api/v1/urls.py` (endpoints)

```python
from django.urls import path

from songify.music.api.v1.views import (
    MusicConversionWebhookAPIView,
    MusicCreateAPIView,
    UserMusicListAPIView,
)

app_name = 'v1'

urlpatterns = [
    path('generate/',   MusicCreateAPIView.as_view(),  name='music_create'),
    path('music-list/', UserMusicListAPIView.as_view(), name='music_list'),
    path('webhook/conversion-details/', MusicConversionWebhookAPIView.as_view(),
         name='music_webhook_conversion_details'),
]
```

Nested `include([...])` groups related routes under a shared prefix:

```python
path('webhooks/', include([
    path('android-rtdn/', AndroidRTDNView.as_view(), name='android-rtdn'),
])),
```

**Resulting URL + reverse name**

| URL | `reverse()` name |
|---|---|
| `/api/music/v1/generate/` | `api:music:v1:music_create` |
| `/api/identity/v1/auth/login/` | `api:identity:v1:device_login` |
| `/api/payment/v1/webhooks/android-rtdn/` | `api:payment:v1:android-rtdn` |

Always reverse by name in tests: `reverse('api:payment:v1:android-rtdn')`.

---

## 4. Naming conventions

### Files & directories

| Thing | Convention | Example |
|---|---|---|
| App package | singular, lowercase, one word | `music`, `billing`, `identity` |
| Module file | `snake_case.py` | `exception_handler.py`, `openai_service.py` |
| Service module | `<vendor>_service.py` | `sunoapi_service.py`, `apple_pay_service.py` |
| Migration | `NNNN_<snake_case_verb_phrase>.py` | `0004_inappproduct_is_featured.py`, `0002_seed_gift_offer_constants.py` |
| Test file | `tests.py` at app root | `songify/payment/tests.py` |

Prefer domain words over Django-generic ones for app names: `identity` (not `users`),
`billing` (catalogue + balances), `payment` (store verification + webhooks).

### Python symbols

| Thing | Convention | Example |
|---|---|---|
| Model | `PascalCase`, singular | `MusicConversion`, `BillingProfile`, `InAppProduct` |
| Abstract base model | `PascalCase` + role suffix | `TimestampModel` |
| Model field | `snake_case` | `album_cover_path`, `vip_end_date` |
| Boolean field | `is_` / `has_` / verb prefix | `is_active`, `is_featured`, `make_instrumental`, `enqueue_success` |
| Timestamp field | `<verb>_at` | `created_at`, `modified_at`, `vip_start_date` |
| Choices class | nested `PascalCase` on the model | `MusicConversion.ConversionStatus` |
| Choice member | `UPPER_SNAKE` | `PENDING`, `COMPLETED` |
| AppConfig | `<App>Config` | `MusicConfig`, `BillingConfig` |
| Admin class | `<Model>Admin` | `MusicConversionAdmin` |
| Service class | `<Vendor>Service` | `SunoAPIService`, `OpenAILyricsService` |
| Exception | `<Domain><Kind>Exception` | `MusicGPTResponseException`, `LyricsConfigurationException` |
| Private helper | leading `_` | `_to_int`, `_normalize_status`, `_build_user_message` |
| Class constant | `UPPER_SNAKE` on the class | `BASE_URL`, `DEFAULT_TIMEOUT_SECONDS` |
| Settings key | `UPPER_SNAKE`, vendor-prefixed | `OPENAI_LYRICS_MODEL`, `ANDROID_PACKAGE_NAME` |

### Views

`<Subject><Action>APIView` — subject first, action second, `APIView` suffix always.

```
MusicCreateAPIView                  POST   create a resource
UserMusicListAPIView                GET    list caller's resources
InAppProductRetrieveAPIView         GET    single item
UserMusicConversionDetailsAPIView   GET/POST detail refresh
MusicConversionWebhookAPIView       POST   inbound provider webhook
DeviceLoginAPIView                  POST   auth
BaseMusicConversionDetailsAPIView   abstract shared parent, `Base` prefix
```

The `User`/`Device` prefix signals the object is scoped to `request.user`.

### Serializers

Name by direction, not just by model — request and response serializers are separate
classes even for the same model.

```
<Subject>RequestSerializer     validates + performs the write in create()
<Subject>ResponseSerializer    ModelSerializer used to render output
<Model>Serializer              plain read/write ModelSerializer (simple cases)
```

Examples: `MusicCreateRequestSerializer`, `MusicConversionResponseSerializer`,
`MusicConversionDetailsRequestSerializer`, `BillingProfileSerializer`, `UserSerializer`.

### URL paths & route names

- Path segments: lowercase, **kebab-case**, always trailing slash — `music-list/`,
  `verify-purchase/google-play/`, `inapp-products/item/`.
- Route `name=`: **snake_case** — `music_create`, `lyrics_document_detail`.
  (Payment webhooks use kebab-case names for historical reasons; pick one and
  stick to it in a new project — snake_case is the majority here.)
- Path params are typed and descriptive: `<int:document_id>`, not `<int:pk>`.

### Quoting & formatting

- Single quotes for strings; double quotes only when the string contains a single quote
  or is a log-message format string.
- ~120 char line limit; wrap long imports in parenthesised multi-line form, alphabetised.
- Import order: stdlib → Django → third-party (DRF, requests) → `songify.*`, blank line
  between groups. Always absolute imports (`from songify.music.models import ...`), never
  relative — except `from .base import *` in settings.
- Never `import *` from a views module in urls.py (one file does; don't copy it).

---

## 5. Layer responsibilities

```
urls.py      → routing + names only
views.py     → HTTP concerns: permissions, method dispatch, status codes,
                catching domain exceptions → Response
serializers  → validation AND the write path (create() does the work)
services/    → all third-party HTTP calls, keys, retries, provider quirks
models.py    → schema + small domain methods (deduct_credit, get_remaining_balance)
signals.py   → cross-app reactions to model saves
utils/       → exceptions + pure helpers
```

**The pattern that ties it together:** the view validates, calls `serializer.save()`,
and translates domain exceptions into responses. The serializer's `create()` orchestrates
service calls and DB writes and returns a **dict** of objects, which the view renders
with response serializers.

```python
class MusicCreateAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MusicCreateRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        logger.info("MusicCreateAPIView request received for user_id=%s", request.user.id)

        try:
            result = serializer.save()
        except InsufficientBalanceException as exc:
            return Response({'detail': exc.detail}, status=exc.status_code)
        except MusicGPTAPIException as exc:
            return Response({'detail': exc.detail}, status=exc.status_code)

        data = {
            'task': MusicGenerationTaskResponseSerializer(result['task']).data,
            'billing_profile': BillingProfileSerializer(result['billing_profile']).data,
        }
        return Response(data, status=status.HTTP_201_CREATED)
```

Extra input the serializer needs beyond the request body is passed through
`serializer.context` before `save()`:

```python
serializer.context['generation'] = generation
serializer.context['is_webhook'] = self.is_webhook
```

Shared multi-endpoint logic goes into a `Base…APIView` with a `NotImplementedError`
hook that subclasses override — that's how the same conversion handler serves both the
authenticated user route (`filter(user=request.user)`) and the open webhook route.

---

## 6. Templates to copy

### `apps.py`

```python
from django.apps import AppConfig


class MusicConfig(AppConfig):
    name = 'songify.music'
```

With signals:

```python
class BillingConfig(AppConfig):
    name = 'songify.billing'

    def ready(self):
        import songify.billing.signals
```

### Abstract timestamp base (`core/models.py`)

```python
class TimestampModel(models.Model):
    created_at = models.DateTimeField(verbose_name=_('created at'), auto_now_add=True)
    modified_at = models.DateTimeField(verbose_name=_('modified at'), auto_now=True)

    class Meta:
        abstract = True
```

### Model

Every field carries a `verbose_name=_('…')`. Text fields use `blank=True` with an
implicit `''` default instead of `null=True`. FKs to `User` are `SET_NULL` +
`null=True` so history survives account deletion; owned children are `CASCADE`.

```python
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from songify.core.models import TimestampModel

User = get_user_model()


class MusicConversion(TimestampModel):
    class ConversionStatus(models.TextChoices):
        PENDING = 'PENDING', _('Pending')
        COMPLETED = 'COMPLETED', _('Completed')
        FAILED = 'FAILED', _('Failed')

    user = models.ForeignKey(
        to=User,
        verbose_name=_('user'),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='music_conversions',
    )
    generation = models.ForeignKey(
        to=MusicGenerationTask,
        verbose_name=_('generation'),
        on_delete=models.CASCADE,
        related_name='conversions',
    )
    title = models.CharField(verbose_name=_('title'), max_length=255, blank=True)
    status = models.CharField(
        verbose_name=_('status'),
        max_length=32,
        choices=ConversionStatus.choices,
        default=ConversionStatus.PENDING,
    )
    metadata = models.JSONField(verbose_name=_('metadata'), default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('MusicConversion')
        verbose_name_plural = _('MusicConversions')

    def __str__(self):
        return f'MusicConversion({self.id})'
```

Conventions: `to=` and `verbose_name=` are always passed as keywords · `related_name` is
plural snake_case and app-qualified enough to be unique across the project · raw provider
payloads are always kept in a `metadata = JSONField(default=dict)` · `__str__` returns
`f'ModelName({identifier})'`.

### Admin

```python
@admin.register(MusicConversion)
class MusicConversionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'user_platform', 'generation__task_id', 'status', 'created_at')
    list_filter = (UserPlatformFilter, 'status', 'created_at', 'modified_at')
    search_fields = ('conversion_id_1', 'generation__task_id')
    readonly_fields = ('created_at', 'modified_at')

    def user_platform(self, obj):
        return obj.user.platform
    user_platform.short_description = 'Platform'
    user_platform.admin_order_field = 'user__platform'
```

Always use the `@admin.register(Model)` decorator, always make timestamps `readonly_fields`.

### Service class

```python
from __future__ import annotations

import logging

import requests
from django.conf import settings

from songify.lyrics.utils.exceptions import (
    LyricsAPIException,
    LyricsConfigurationException,
    LyricsResponseException,
)

logger = logging.getLogger(__name__)


class OpenAILyricsService:
    BASE_URL = 'https://api.openai.com/v1/'
    COMPLETIONS_ENDPOINT = 'chat/completions'
    DEFAULT_TIMEOUT_SECONDS = 30
    DEFAULT_MODEL = 'gpt-4o-mini'

    def __init__(self) -> None:
        self.base_url = self.BASE_URL
        self.timeout = self.DEFAULT_TIMEOUT_SECONDS
        self.api_key = getattr(settings, 'OPENAI_API_KEY', '').strip()
        if not self.api_key:
            raise LyricsConfigurationException(
                detail='OpenAI API key is not configured.',
                status_code=500,
            )
```

Endpoints, timeouts and defaults are **class constants**, never inline literals.
Credentials are read from `settings` inside `__init__` (via `getattr` with a default) and
validated immediately — a misconfigured key fails at construction, not mid-request.

### Provider factory (`services/factory.py`)

Swap vendors with an env var, no code change:

```python
from django.conf import settings

from songify.music.services.musicgpt_service import MusicGPTService
from songify.music.services.sunoapi_service import SunoAPIService


def get_music_service():
    provider = str(getattr(settings, 'MUSIC_PROVIDER', 'musicgpt') or '').strip().lower()
    if provider == 'suno':
        return SunoAPIService()
    return MusicGPTService()
```

### Exceptions (`utils/exceptions.py`)

Subclass DRF's `APIException` so the status code travels with the error. A per-app base
class lets views catch one type and get the whole family.

```python
from rest_framework.exceptions import APIException


class InsufficientBalanceException(APIException):
    status_code = 402
    default_detail = 'Insufficient credit balance.'
    default_code = 'insufficient_credit_balance'


class MusicGPTAPIException(APIException):          # ← app-level base
    status_code = 502
    default_detail = 'MusicGPT request failed.'
    default_code = 'musicgpt_error'

    def __init__(self, detail: str, status_code: int):
        self.status_code = status_code
        super().__init__(detail=detail)


class MusicGPTConfigurationException(MusicGPTAPIException):
    status_code = 500
    default_detail = 'MusicGPT configuration is invalid.'
    default_code = 'musicgpt_config_error'
```

Error responses are always `{'detail': '<message>'}`.

### Tests

```python
from django.test import override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase

from songify.payment.models import GooglePlayNotification

RTDN_URL = reverse('api:payment:v1:android-rtdn')


@override_settings(ANDROID_PACKAGE_NAME='com.songify.app')
class AndroidRTDNAckTests(APITestCase):
    """Docstring states the contract being protected, not what the code does."""

    def test_invalid_package_name_acks_200_and_persists_raw(self):
        resp = self.client.post(RTDN_URL, payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
```

`APITestCase` + reversed URL constants at module level + long descriptive
`test_<condition>_<expected_outcome>` names.

---

## 7. Settings conventions

- `base.py` holds everything; `local.py` / `production.py` are `from .base import *`
  plus a handful of overrides. Never duplicate a setting into both.
- Environment via `django-environ`, read once at the top of `base.py`:
  ```python
  env = environ.Env()
  env.read_env(str(BASE_DIR / '.env'))
  ```
- Typed accessors always: `env.bool(...)`, `env.str(...)`, `env.db('DATABASE_URL')`.
  Anything optional gets `default=`; anything mandatory omits it so boot fails loudly.
- `INSTALLED_APPS` is grouped with comments: Django contrib → `# Third-party apps` →
  `# My apps`.
- Vendor settings are grouped at the bottom of `base.py` under a `# <Vendor>` comment.
- File-path settings are normalised to absolute at import time:
  ```python
  _key = Path(env.str('GOOGLE_PLAY_SERVICE_ACCOUNT_FILE'))
  GOOGLE_PLAY_SERVICE_ACCOUNT_FILE = str(_key if _key.is_absolute() else (BASE_DIR / _key).resolve())
  ```
- Custom user model is declared from day one: `AUTH_USER_MODEL = 'identity.User'`
  (app **label** only — no `songify.` prefix here).
- DRF config in one `REST_FRAMEWORK` dict, including a project-wide exception handler:
  ```python
  REST_FRAMEWORK = {
      'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.TokenAuthentication'],
      'EXCEPTION_HANDLER': 'songify.core.api.exception_handler.validation_error_log_handler',
  }
  ```
- Behaviour flags get an env var + an inline comment explaining when to flip them
  (e.g. `REJECT_WEAK_DEVICE_ID`).
- `LOGS_DIR.mkdir(parents=True, exist_ok=True)` at import so logging never fails on a
  fresh checkout. Rotating file handler at 25 MB × 5; `django.request` pinned to `ERROR`
  so routine 4xx don't flood the log; `django.server` console-only.

---

## 8. The `core` app

Every project gets one. It owns the things other apps import but that belong to no
single domain:

- `core/models.py` — `TimestampModel` abstract base, `Constant` key/value model.
- `core/constants.py` — `Constant` class of defaults + `get_constant(key, data_type)`
  that reads from the DB and self-seeds from the class on first miss.
- `core/utils.py` — `get_logger()`, request/header formatters, `truncate(value, limit=200)`
  for keeping large payloads out of logs.
- `core/api/exception_handler.py` — the DRF `EXCEPTION_HANDLER`, logs 400s with full
  request context.
- `core/api/v1/` — remote-config endpoints exposing `Constant` rows to the client.

**Logging hygiene, non-negotiable:** never log an `Authorization` value — log presence
only (`'<set>' / '<none>'`), and run every user-controlled payload through `truncate()`.

---

## 9. Adding a new app — checklist

1. `python manage.py startapp <app>` then move the folder into `songify/`.
2. `apps.py`: set `name = 'songify.<app>'`, rename the class to `<App>Config`.
3. Add `'songify.<app>'` to `INSTALLED_APPS` under `# My apps`.
4. `mkdir -p songify/<app>/api/v1` and add `__init__.py` in both.
5. Create `api/urls.py` (`app_name = '<app>'`, includes `v1`) and
   `api/v1/urls.py` (`app_name = 'v1'`).
6. Mount it in `config/urls.py` inside `api_url_patterns`.
7. Models inherit `TimestampModel`; `makemigrations <app>`.
8. Register everything in `admin.py` with `@admin.register`.
9. Third-party calls → `services/<vendor>_service.py`; errors →
   `utils/exceptions.py` subclassing `APIException`.
10. New env vars → `.env.example` with a `<placeholder>` **and** `base.py` with a typed
    `env.*()` read.

---

## 10. Quick reference

```bash
# setup
python -m venv venv && source venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env                       # then fill it in

# run
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver

# production settings
DJANGO_SETTINGS_MODULE=config.settings.production python manage.py check --deploy

# tests
python manage.py test                      # all
python manage.py test songify.payment      # one app
```
