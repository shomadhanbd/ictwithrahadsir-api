# ictwithrahadsir-api

Django + Django REST Framework backend for the ICT with Rahad Sir platform.
It is a **drop-in replacement API** for the existing `ictwithrahadsir-client`
and `ictwithrahadsir-admin` Next.js apps — routes, request/response shapes,
pagination envelope, and error format all match what those two frontends
already call, so neither frontend needs code changes to point at this
backend (just set `BACKEND_URL` / `NEXT_PUBLIC_BACKEND_URL` to this API's
`/api` base URL).

## Stack

- Django 5 + Django REST Framework
- PostgreSQL in production (via `DATABASE_URL`), SQLite fallback for
  zero-config local dev
- Token authentication (`Authorization: Token <key>`) — one token per user,
  issued on login/registration
- Storage: local disk by default; flip `USE_S3=True` + AWS/DigitalOcean
  Spaces credentials to switch to S3-compatible object storage with no code
  changes (`django-storages`)
- OTP delivery: pluggable `SmsBackend` (`apps/core/services/`), defaults to a
  console/log backend so the whole auth flow works without a real SMS
  gateway account

## Project layout

```
apps/
  core/        infrastructure only: DRF plumbing (auth, pagination,
               permissions, throttling, fields, error envelope), slugs,
               middleware, SMS services, uploads, management commands
  identity/    User (phone+OTP and email+password auth), OTP, admin user CRUD
  faculty/     Teacher roster and CourseInstructor, their per-course
               assignment with commission
  courses/     Course, CourseCategory, CoursePrice, Coupon, Routine,
               Section/Content tree, Enrollment, CourseMaterial
  assessment/  Exam, QuestionBank, Question, ExamAttempt -- exam taking,
               results and ranking
  billing/     Order, Payment, and the admin dashboard aggregates
  store/       Product and CartItem, the catalogue and basket
  content/     Notice, static Page, Testimonial, Advertisement, EBook,
               homepage aggregate (`/home`)
  support/     Contact messages -- the staff inbox behind the contact form

Each app owns one domain and is named after it. Apps depend downward only:
billing and store depend on courses, courses never depends on them (see
apps/courses/selectors.py for the one inverted read).
```

Every `/admin/*` endpoint requires a token belonging to a `staff`, `admin`,
or `instructor` user (`apps.core.api.permissions.IsAdminRole`). Everything else
is public read / authenticated write per-resource, matching how the existing
frontends already call the API.

## Where this deviates from PROJECT_STRUCTURE.md

`PROJECT_STRUCTURE.md` is a reusable blueprint from another project. This
codebase follows it -- split settings, split requirements, per-app
`api/v1/` packages, three-tier routing with `api:<app>:v1:<name>` reverse
names, rotating file logging -- with these deliberate exceptions:

| Blueprint | Here | Why |
|---|---|---|
| project package named after the project | `apps/` | project decision |
| `/api/<app>/v1/…` URLs | `/api/v1/…`, resource-oriented | the API should not advertise which Django app owns what, so models can move between apps without breaking a client -- which is exactly what the re-decomposition then did |
| `created_at` / `modified_at` | `created_at` / `updated_at` | exposed in serializers and read by both frontends |
| `verbose_name=_()` on every field | omitted | ~260 fields, migrations in every app, no functional gain |
| all endpoints as `APIView` | ~20 `ModelViewSet`s retained | router-generated CRUD; converting loses it for nothing |
| `{'detail': …}` errors | `{message, errors}` | both frontends parse the Laravel-style envelope |

Three guards exist because of the above and should not be worked around:

- `apps/core/url_contract.txt` snapshots every served path.
  `manage.py dump_url_contract` regenerates it, and should only be run when
  a path change is intended.
- `apps/core/test_response_shapes.py` pins response *bodies*, which the URL
  contract does not cover. It lives in `core` because several of its
  assertions span apps.
- `apps/core/test_query_budget.py` pins the *cost* of the read-heavy
  endpoints, which neither of the above covers — a response is correct
  whether it took 4 queries or 400. Each endpoint asserts a query ceiling,
  and `ScaledQueryBudgetTests` repeats every assertion against twice the
  data: identical counts at both sizes is what proves an endpoint is flat
  rather than merely small today. If one fails, something became per-row;
  raise the number only deliberately, with a reason.

### Query-cost conventions

Serializers that need per-row aggregates take them from a batch in
`context` and fall back to a per-object query when it is absent, so the
same serializer is cheap in a list and still correct for a single object.
`build_course_stats`, `build_section_tree` and `build_category_children`
(all in `apps/courses/api/v1/serializers.py`) are the three of these; a
view that serializes many rows should pass the matching one. Anything that
recurses — the section tree, the category tree — must be grouped in Python
from a whole-tree query rather than asking per node.

## Getting started (local dev, no external services)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser   # prompts for phone, email, name, password
python manage.py runserver
```

The API is served at `http://localhost:8000/api/...`. Django's own admin
site (separate from the platform's `/admin/*` API routes) is at
`/django-admin/`.

With no `DATABASE_URL` set, it runs on a local `db.sqlite3` — good enough
for development. Set `DATABASE_URL=postgres://user:pass@host:5432/dbname` to
point at real Postgres.

## Docker

```bash
docker compose up --build
```

Runs Postgres + the API (migrations and `collectstatic` run automatically on
container start). Copy `.env.example` values into a `.env` file or export
them before running to override the defaults baked into `docker-compose.yml`.

## Switching on real integrations later

- **Object storage**: set `USE_S3=True` plus `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_STORAGE_BUCKET_NAME`, `AWS_S3_REGION_NAME`,
  `AWS_S3_ENDPOINT_URL` (DigitalOcean Spaces or S3). No code changes needed —
  every image/file field already goes through `apps.core.api.fields.MediaField`
  and the `/aws-upload-url` presigned-upload endpoint.
- **SMS/OTP gateway**: implement a class in `apps/core/services/` extending
  `SmsBackend`, register it in `get_sms_backend()`'s `backends` dict, and set
  `SMS_BACKEND=<name>` in `.env`. Until then, OTP codes are logged to the
  server console/log instead of being texted.
- **Payments**: the platform uses manual mobile-banking confirmation
  (student submits a transaction ID, an admin verifies it from
  `/admin/payment`) rather than an automated gateway — this matches how the
  existing frontends are built. Approving a payment auto-enrolls the student
  in the paid course.

## Key request/response conventions (matched from the existing frontends)

- List endpoints return Laravel's pagination envelope:
  `{data, links: {first,last,prev,next}, meta: {current_page,last_page,per_page,total,...}}`.
  `meta.links` (the numbered page buttons) is a *window* around the current
  page with `...` for the elided runs, not one entry per page as Laravel
  emits: at 50k rows the full list was thousands of link objects and several
  hundred KB of JSON on every request. Both frontends paginate off
  `meta.last_page` and read neither the count nor the contents of
  `meta.links`. Widen it with `page_link_window` if a client ever needs more.
- Validation errors return `422` with `{message, errors: {field: [msg, ...]}}`.
- Every image/file field serializes as `{id, link}`; write it as either a
  multipart file upload or a URL string obtained from `/aws-upload-url`.
- Multipart admin updates that can't use a real HTTP verb send
  `POST .../{id}?_method=PUT` (or `PATCH`) — handled transparently by
  `apps.core.middleware.MethodOverrideMiddleware`.
- Routes have no trailing slash (`APPEND_SLASH=False`), matching both
  frontends' hardcoded paths.
