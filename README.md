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
- Token authentication (`Authorization: Bearer <key>`) — one token per user,
  issued on login/registration. The `Bearer` keyword (not DRF's default
  `Token`) is what both frontends send; see
  `apps.core.api.authentication.BearerTokenAuthentication`
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

Endpoints that instructors must *not* reach layer something stricter on top:
`IsFullAdmin` for admin-only resources, or a resource-specific permission
such as `apps.identity.api.v1.permissions.CanManageUsers`, which lets an
instructor manage students but not admins and not deletions. Those rules
belong in a permission class and nowhere else -- a serializer only runs on
create and update, so guards written there do not cover `DELETE`.

## Architecture

See **[ARCHITECTURE.md](ARCHITECTURE.md)** for the internal layering — which
layer owns what, the dependency rules between apps, naming conventions, the
query-cost rules, and the three test guards that pin the API contract.

Read it before adding an endpoint.

## API documentation

The OpenAPI schema is generated from the serializers, so it cannot drift from
the code the way a hand-written document would.

| URL | What |
|---|---|
| `/api/docs/` | Swagger UI — browse and try every endpoint |
| `/api/redoc/` | ReDoc — the same schema, read-optimised |
| `/api/schema/` | The raw OpenAPI 3 document |

`manage.py spectacular --file schema.yaml` writes it out. It currently
generates with **zero errors**; keep it that way. A new `APIView` that
neither declares `serializer_class` nor carries `@extend_schema` will emit an
error and be omitted from the docs entirely.

There are four standing warnings, all of them enum-naming collisions between
same-named choice fields on unrelated models (`type` on `Content`/`Teacher`,
`status`, `Coupon.discount_type`). They are cosmetic -- the schema is correct
-- and clearing them means adding `ENUM_NAME_OVERRIDES` to
`SPECTACULAR_SETTINGS`. Treat the count as the baseline: a fifth warning is a
new problem.

## Code style

`ruff` is the linter and formatter; its configuration is in `pyproject.toml`
at the repo root. It is pinned in `requirements/local.txt`, never in
`base.txt`, so production images stay free of it.

```bash
ruff check .          # lint
ruff check . --fix    # lint, applying the safe autofixes
ruff format .         # format
```

## Getting started (local dev, no external services)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/local.txt   # or requirements/production.txt
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
- Routes carry a trailing slash, and `APPEND_SLASH=False` is set. Those two
  together mean a request to a slash-less path **404s rather than being
  redirected**, so clients must call the paths exactly as
  `apps/core/url_contract.txt` lists them.
