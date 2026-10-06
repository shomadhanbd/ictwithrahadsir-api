# ictwithrahadsir-api

Django REST Framework backend for the ICT with Rahad Sir platform. It is a
drop-in API for the `ictwithrahadsir-client` and `ictwithrahadsir-admin`
Next.js apps: routes, payload shapes, the pagination envelope and the error
format all match what those frontends already call. Point them at it with
`BACKEND_URL` / `NEXT_PUBLIC_BACKEND_URL` set to this API's `/api` base URL.

## Stack

- Django 6.1 + Django REST Framework
- PostgreSQL in production, SQLite locally when `DATABASE_URL` is unset
- Redis cache in production, for rate limits and OTP state
- Token auth sent as `Authorization: Bearer <key>`, one token per user
  (`apps.core.api.authentication.BearerTokenAuthentication`)
- SMS through BulkSMSBD; locally a console backend logs messages instead
- Payments through SSLCommerz

## Getting started

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements/local.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser   # prompts for phone, email, name, password
python manage.py seed_demo         # optional: fills the database with demo data
python manage.py runserver
```

No external service is needed locally: SQLite, an in-process cache, OTP codes
in the console log, and the SSLCommerz sandbox.

- API: `http://localhost:8000/api/` — `public/` for the client app,
  `private/` for the back office
- Django admin: `http://localhost:8000/admin/`

## Settings

`config/settings/` has three modules:

| Module | Used by | Purpose |
|---|---|---|
| `base.py` | both below | Everything shared, and the app's fixed rules (OTP limits, token lifetime, throttle rates) |
| `local.py` | `manage.py` (default) | `DEBUG`, every host and origin allowed, payment sandbox, the `demo` app |
| `production.py` | `wsgi.py` / `asgi.py` (default) | HTTPS hardening, stdout logging, and boot checks |

Per-server values and secrets come from `.env` (template: `.env.example`).
Production refuses to start if any of these is missing or unsafe:

- `SECRET_KEY` (not a placeholder), `ALLOWED_HOSTS`
- `DATABASE_URL` (Postgres, not SQLite), `CACHE_URL` (Redis, not locmem)
- `SMS_BACKEND=bulksmsbd`
- `SSLCOMMERZ_STORE_ID`, `SSLCOMMERZ_STORE_PASSWORD`
- `API_BASE_URL`, `FRONTEND_URL` and the three `SSLCOMMERZ_*_REDIRECT` URLs,
  all `https://`

These are read at import, so build steps such as `collectstatic` need them too
(placeholders will do).

## Deployment

`manage.py` defaults to the local settings, so on the server every command,
including migrations, `collectstatic` and cron, names the production module:

```bash
DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py migrate
```

**Health probe**: `GET /api/health/` reports whether the database and cache
answer (503 if not). It runs before the host and HTTPS checks, so a load
balancer can probe it by IP over plain HTTP.

**Proxy**: production assumes one TLS-terminating proxy that sets
`X-Forwarded-Proto`. Throttles key on the client IP behind `NUM_PROXIES`
proxies (default 1).

### Scheduled jobs

```
# Submit and mark exam attempts whose time ran out.
* * * * * cd /path/to/backend && DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py finalize_exam_attempts
# Clear old OTP codes (keeps the last hour, which the per-phone send cap counts).
0 * * * * cd /path/to/backend && DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py purge_expired_otps
# Text students whose access ends within EXPIRY_REMINDER_DAYS, with a renew link to FRONTEND_URL.
0 9 * * * cd /path/to/backend && DJANGO_SETTINGS_MODULE=config.settings.production venv/bin/python manage.py send_expiry_reminders
```

`refresh_question_counts` recounts the question bank's cached counts. It is a
repair tool, also available at `POST /api/private/question-counts/refresh/`,
not a scheduled job.

## Project layout

```
apps/
  core/        infrastructure: DRF plumbing (auth, pagination, permissions,
               throttling, fields, error envelope), slugs, phones, SMS,
               middleware, health check
  academic/    ClassLevel, Group, Subject, Chapter, Topic, Batch: the
               curriculum and the admin-managed lists profiles are tagged with
  profiles/    TeacherProfile, StudentProfile, GuardianProfile: who a person
               is, as distinct from how they sign in
  identity/    User (phone + OTP and email + password), OTP, admin user CRUD
  courses/     Course, Routine, Section/Content tree, Enrollment,
               CourseMaterial, CourseTeacher. Courses carry no prices
  question/    the question bank: sources, blocks, sets, questions, options
  exam/        exams assembled from the question bank, and students'
               attempts, auto-grading, results and ranking
  billing/     Product (a package of courses at a price) and Payment (one
               SSLCommerz checkout). All pricing lives here
  content/     Notice, Page, Testimonial, Advertisement, EBook, the homepage
  dashboard/   back-office summary and charts (no models)
  demo/        the `seed_demo` command; installed by the local settings only
```

### Dependencies between apps

Each app owns one domain and depends downward only:

- `core` is infrastructure. The one domain module it imports is
  `apps.identity.roles` (plain role names), which its permission tiers use.
- `academic` and `profiles` sit below `identity`: `profiles` reaches the user
  only through `settings.AUTH_USER_MODEL`, and `identity` imports `profiles`,
  never the reverse. Tests will not catch that arrow being flipped, so watch
  for it in review.
- `billing` depends on `courses`, never the other way. Where a lower app needs
  a higher one's answer (courses asking billing for prices, question asking
  exam which blocks are unreleased), the higher app registers a function in
  `apps.core.providers` at startup and the lower one looks it up.
- `demo` is the top: it imports every domain app and nothing imports it.

## Permissions

Every `/api/private/*` endpoint requires a token for a role its permission
tier allows (`apps.core.api.permissions`). Public endpoints are open to read
and require sign-in to write, per resource.

Endpoints teachers must not reach add something stricter: `IsFullAdmin`, or
a resource-specific class such as
`apps.identity.api.permissions.CanManageUsers`. These rules belong in a
permission class only: a serializer runs on create and update, so a guard
there does not cover `DELETE`.

The rules, each enforced in one place and mirrored by the admin panel:

- **Accounts**: only a superuser changes a superuser's account, on every path
  that writes one (user API, teachers API, Django admin):
  `apps.core.api.permissions.may_change_account`.
- **Curriculum**: teachers build and edit their courses and the question bank.
  Deleting any part of a course (`IsCourseTeacherAdminDeletes`), changing a
  class level, moving a node to another parent and switching a subject off
  (`AdminOnlyFieldsMixin`) are an admin's.
- **Enrolments**: granting, changing or removing one is an admin's; a teacher
  records cash sales.
- **Practice**: a chapter's questions appear on the free practice page only
  once `Chapter.practice_enabled` is on (off by default).
- **Published papers** are final: their structure and prices do not change,
  and one cannot be published with a result time but no end time.

## Payments

Everything is sold as a billing `Product`, shown to admins and students as a
*package*: one or more courses at a price, for a number of days, until a date,
or for life. A course is for sale when an active package includes it; its
catalogue `price` is the cheapest such package, and `is_free` means one costs
৳0.

Register `<API_BASE_URL>/api/public/payments/ipn/` as the IPN URL in the
SSLCommerz merchant panel. The flow:

1. `GET /api/public/products/?course=<slug>` lists the packages a course is
   sold in (the course detail payload carries them as `packages` too).
2. `POST /api/public/payments/initiate/` with `{product_id}` creates a
   `Payment` and returns `gateway_page_url`; send the student there. A ৳0
   package is VALID at once, which is how a free course is claimed.
3. SSLCommerz posts to `payments/capture/`, which redirects the browser to
   `SSLCOMMERZ_SUCCESS|FAIL|CANCEL_REDIRECT?tran_id=`, and to the IPN. Both
   are signature-checked, and a VALID is confirmed with the Validator API
   before it is stored. A VALID payment enrols the student on every course in
   the package and texts them once; access never shortens.

- **Cash sales**: staff record money taken at the centre with
  `POST /api/private/payments/cash/` (`method=cash`). It enrols like an online
  payment; without `valid_till` it lasts as long as the package does.
- **Stuck payments**: settle a payment confirmed in the SSLCommerz panel with
  the Django admin's "Mark paid and grant access" action. Status and amount are
  not editable by hand.
- **Duplicates**: a second paid checkout for a package whose access is still
  running is marked `refund_due` and grants nothing.
- **Refunds and chargebacks are not handled.** Refund a `refund_due` payment in
  the SSLCommerz panel. A payment refunded there for any other reason stays
  VALID here, so end the student's access by removing the enrolment.
- **Coupons** are not built yet.

## Course exams

Adding a lesson of type `exam` creates a draft `exam.Exam` (scope `course`)
owned by it, built and published at `/api/private/exams/<id>/`. Only MCQ parts
are allowed for now, graded automatically. Anyone who may open the lesson may
sit the exam once it is published:

1. `GET /api/public/exams/<slug>/`: the exam and my attempts (the lesson
   payload's `exam` key carries the same summary).
2. `POST /api/public/exams/<slug>/attempts/`: start, or resume the open one.
3. `GET /api/public/exam-attempts/<id>/`: the paper (no answer key) and my
   saved answers. `PUT .../answers/` autosaves; `POST .../submit/` finishes.
   An attempt past its deadline is submitted as it stands when next read.
4. `GET /api/public/exam-attempts/<id>/result/` and
   `GET /api/public/exams/<slug>/ranking/`: once `result_publish_time` has
   passed. The first submitted attempt is the official, ranked one.

Admins see submissions at `GET /api/private/exams/<id>/attempts/` and re-mark
them after fixing an answer key with `POST .../regrade/`.

## API conventions

These match what the existing frontends expect.

- **Pagination**: lists return Laravel's envelope,
  `{data, links: {first, last, prev, next}, meta: {current_page, last_page, per_page, total, ...}}`.
  `meta.links` is a window around the current page with `...` for gaps, not
  one entry per page; widen it with `page_link_window` if a client needs more.
- **Validation errors**: `422` with `{message, errors: {field: [msg, ...]}}`.
- **Files**: every image or file field reads as `{id, link}` and is written as
  a URL string. There is no file upload.
- **Method override**: a multipart admin update that can't use a real verb
  sends `POST .../{id}?_method=PUT` (or `PATCH`), handled by
  `apps.core.middleware.MethodOverrideMiddleware`.
- **Trailing slashes**: every route ends in `/` and `APPEND_SLASH=False`, so a
  slash-less path 404s instead of redirecting.

## Development

```bash
python manage.py test   # full suite
ruff check .            # lint (ruff check . --fix applies safe fixes)
ruff format .           # format
```

`ruff` is configured in `pyproject.toml` and installed from
`requirements/local.txt` only, so production images stay free of it.

Two test suites pin the API contract; don't relax them to make a change pass:
`test_response_shapes` (the frozen payload keys) and `test_query_budget` (the
per-endpoint query ceilings).
