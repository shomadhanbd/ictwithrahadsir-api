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
- OTP delivery: pluggable `SmsBackend` (`apps/core/sms.py`), defaults to a
  console/log backend so the whole auth flow works without a real SMS
  gateway account

## Project layout

```
apps/
  core/        infrastructure only: DRF plumbing (auth, pagination,
               permissions, throttling, fields, error envelope), slugs,
               phone parsing, middleware, SMS services
  academic/    Subject, ClassLevel and Group (science/arts/commerce) -- the
               small admin-managed lists the profiles are tagged with
  profiles/    TeacherProfile, StudentProfile and GuardianProfile: who a
               person is, as distinct from how they sign in
  identity/    User (phone+OTP and email+password auth), OTP, admin user CRUD
               -- authentication and nothing else
  courses/     Course, CourseCategory, CoursePrice, Coupon, Routine,
               Section/Content tree, Enrollment, CourseMaterial, and
               CourseTeacher, a teacher's assignment to one course
  question/    the question bank: blocks, stimulus sets, questions, options
  exam/        exam authoring -- papers assembled from the question bank
  billing/     Product (a one-time bundle of courses), ProductCoupon, Order,
               Payment, and the SSLCommerz client
  content/     Notice, static Page, Testimonial, Advertisement, EBook,
               homepage aggregate (`/home`)
  demo/        the `seed_demo` command; sits above every domain app

Each app owns one domain and is named after it. Apps depend downward only:
billing depends on courses, courses never depends on it (see
apps/courses/selectors.py for the one inverted read).

`profiles` sits *below* `identity`, not above it: it reaches the user only
through `settings.AUTH_USER_MODEL` and imports nothing from `identity`, while
`identity`'s serializers import it to keep emitting the nested `student` block.
That one-way arrow is what keeps the two acyclic -- reversing it is the failure
mode to watch for, and `python manage.py test apps.core` will not catch it.
```

Every `/api/private/*` endpoint requires a token for a role allowed by its
permission tier (`apps.core.api.permissions`). Everything else
is public read / authenticated write per-resource, matching how the existing
frontends already call the API.

Endpoints that teachers must *not* reach layer something stricter on top:
`IsFullAdmin` for admin-only resources, or a resource-specific permission
such as `apps.identity.api.v1.permissions.CanManageUsers`, which lets an
teacher manage students but not admins and not deletions. Those rules
belong in a permission class and nowhere else -- a serializer only runs on
create and update, so guards written there do not cover `DELETE`.

## Architecture

Apps depend downward only. `core` is infrastructure and imports no domain app;
`academic` and `profiles` sit below `identity`, which imports them rather than
the reverse; `billing` depends on `courses`, never the other way
(see `apps/courses/selectors.py` for the one inverted read). `demo` is the
top: it imports every domain app and nothing imports it.

Two test guards pin the contract and should not be relaxed to make a change
pass: `test_response_shapes` (the frozen payload key lists) and
`test_query_budget` (the per-endpoint query ceilings).

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

It also generates with zero warnings. A new choice field that shares a name
(`status`, `type`) with another model's gets a hash-named enum and a warning;
name it in `ENUM_NAME_OVERRIDES` in `SPECTACULAR_SETTINGS`.

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

## Switching on real integrations later

- **SMS/OTP gateway**: implement a class in `apps/core/sms.py` extending
  `SmsBackend`, register it in the `BACKENDS` dict, and set
  `SMS_BACKEND=<name>` in `.env`. Until then, OTP codes are logged to the
  server console/log instead of being texted.
- **Payments**: every purchase, course or product, goes through SSLCommerz
  (`apps/billing/sslcommerz.py`). Set `SSLCOMMERZ_STORE_ID`,
  `SSLCOMMERZ_STORE_PASSWORD`, `SSLCOMMERZ_SANDBOX`, `API_BASE_URL` and
  `PAYMENT_RESULT_URL` in `.env`, and register
  `<API_BASE_URL>/api/public/payments/sslcommerz/ipn/` as the IPN URL in the
  merchant panel. The flow:
  1. `POST /api/public/orders/` with `{course_id, price_id}` or `{product_id}`,
     plus an optional `coupon_code` (`POST /api/public/orders/quote/` prices it
     first without placing anything).
  2. `POST /api/public/orders/<id>/pay/` returns `gateway_url`; send the
     student there. A 100% coupon completes the order with no gateway.
  3. SSLCommerz posts back to `payments/sslcommerz/success|fail|cancel/`
     (which redirect the browser to `PAYMENT_RESULT_URL?order_id=&status=`)
     and to the IPN. A payment is settled only from SSLCommerz's validation
     API, never from what a callback posts. Settling a course enrols the
     student for the price's validity; settling a product enrols them on
     every course it unlocks for the product's validity. A purchase never
     shortens access a student already has.
  4. A payment SSLCommerz flags as risky, or whose amount or currency does not
     match, stays pending for an admin to confirm or fail (`PATCH
     /api/private/payments/<id>/` or the Django admin actions).

  The manual bKash/Nagad/Rocket flow is retired; its old payments remain as
  history.

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
- Every image/file field serializes as `{id, link}` and is written as a URL
  string. There is no file upload in this version.
- Multipart admin updates that can't use a real HTTP verb send
  `POST .../{id}?_method=PUT` (or `PATCH`) — handled transparently by
  `apps.core.middleware.MethodOverrideMiddleware`.
- Routes carry a trailing slash, and `APPEND_SLASH=False` is set. Those two
  together mean a request to a slash-less path **404s rather than being
  redirected**, so clients must call the paths exactly as the OpenAPI
  schema lists them.
