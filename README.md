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
- OTP delivery: pluggable `SmsBackend` (`apps/core/sms.py`), defaults to a
  console/log backend so the whole auth flow works without a real SMS
  gateway account

## Project layout

```
apps/
  core/        shared infra: pagination, error envelope, media field/upload
               endpoint, permissions, dashboard aggregates, SMS backend
  accounts/    User model (phone+OTP and email+password auth), admin user CRUD
  team/        Teacher/founder roster
  courses/     Categories, Course, Price, Coupon, Routine, Instructor,
               Section/Content tree, enrollment (CourseUser)
  exams/       MCQ question bank (McqStore/McqQuestion), exam taking +
               results + ranking
  shop/        Product, Cart, Order, manual bKash/Nagad/Rocket Payment
  cms/         Notice, static Page, Testimonial, Advertisement, EBook,
               Contact messages, homepage aggregate (`/home`)
```

Every `/admin/*` endpoint requires a token belonging to a `staff`, `admin`,
or `instructor` user (`apps.core.permissions.IsAdminRole`). Everything else
is public read / authenticated write per-resource, matching how the existing
frontends already call the API.

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
  every image/file field already goes through `apps.core.fields.MediaField`
  and the `/aws-upload-url` presigned-upload endpoint.
- **SMS/OTP gateway**: implement a class in `apps/core/sms.py` extending
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
- Validation errors return `422` with `{message, errors: {field: [msg, ...]}}`.
- Every image/file field serializes as `{id, link}`; write it as either a
  multipart file upload or a URL string obtained from `/aws-upload-url`.
- Multipart admin updates that can't use a real HTTP verb send
  `POST .../{id}?_method=PUT` (or `PATCH`) — handled transparently by
  `apps.core.middleware.MethodOverrideMiddleware`.
- Routes have no trailing slash (`APPEND_SLASH=False`), matching both
  frontends' hardcoded paths.
