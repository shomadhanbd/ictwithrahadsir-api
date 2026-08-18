# Architecture

How this codebase is laid out and, more importantly, **where a given piece of
code belongs**. Read this before adding an endpoint.

`README.md` covers running the project and the API's wire conventions. This
document covers the internal layering.

> This file replaces `PROJECT_STRUCTURE.md`, which was a blueprint copied from
> an unrelated project (Songify). It described a package layout this repo does
> not use, app names that no longer exist, and a layering rule — "the write
> path lives in the serializer's `create()`" — that contradicts how this code
> is actually organised. It was removed rather than corrected, because a stale
> convention doc is worse than none.

---

## 1. Layers

Code belongs to exactly one of these. When you are unsure where something
goes, the question to ask is *"what would I have to mock to test this?"*

```
urls.py       routing and route names only

views.py      HTTP only. Permissions, method dispatch, status codes.
              Reads input through a serializer, calls a service or selector,
              renders the result through a serializer.
              -> No ORM queries. No business rules.

serializers   Input validation and output rendering.
              *RequestSerializer validates what comes in.
              *Serializer / *ResponseSerializer renders what goes out.
              -> No writes that span more than one model.

services.py   Writes. Anything that changes state, especially across models
              or across apps. Owns `transaction.atomic`.
              -> Pure Python in, model instances out. No `request`, no
                 `Response`, no HTTP status codes.
              -> Rule violations are raised as DRF `ValidationError`. See
                 "Why services raise DRF exceptions" below.

selectors.py  Reads that cross an app boundary, or that more than one view
              needs. Returns querysets or plain data.

managers.py   Reusable queryset predicates: `.active()`, `.paid()`,
              `.current()`, `.students()`. If the same `filter(...)` appears
              in two places, it belongs here.
              -> **Every** custom Manager/QuerySet lives here, including the
                 `AUTH_USER_MODEL` one. `models.py` describes the schema; how
                 it is queried is a separate concern.

models.py     Schema, plus small single-object domain methods.
              -> No network or filesystem I/O.

signals.py    Reactions to a model save that must happen however the row was
              written. Denormalisation and propagation only -- never a
              business operation. See "Signals" below.
```

**The rule that matters most:** a view should read as a short list of steps.
If a handler is longer than about fifteen lines, the business logic in it
belongs in `services.py` and the payload assembly belongs in a serializer.

### A view in its finished shape

```python
class OrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OrderCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = create_order(user=request.user, **serializer.validated_data)
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)
```

Validation is the serializer's job, the state change is the service's job, and
the view only wires them together and picks the status code.

### Why services raise DRF exceptions

A service raises `rest_framework.exceptions.ValidationError` for a broken
business rule ("only 2 left in stock", "this order has already been paid")
rather than a hand-rolled domain exception.

That is a deliberate trade. Every error in this project already flows through
`apps/core/api/exception_handler.py`, which renders it as the
`{message, errors}` envelope both frontends parse. A parallel hierarchy of
domain exceptions would have to be caught and re-raised as exactly that DRF
exception at every call site, which buys purity and costs a translation layer
nobody would maintain.

The line that does matter is kept: services never touch `request`, never
build a `Response`, and never choose a status code.

### Signals

There are exactly two receivers, both in `signals.py` files wired from their
`AppConfig.ready()`. The test for whether something belongs here is narrow:

> Does this have to happen no matter *how* the row was written, and is it
> keeping data consistent rather than deciding something?

Both current receivers pass it:

| Receiver | Keeps consistent |
|---|---|
| `apps/faculty/signals.py` | A renamed `Teacher` reaches the `CourseInstructor` rows that had not overridden the field. Otherwise every course page shows the old name for good. |
| `apps/courses/signals.py` | A `Content` moved to another course takes its `ContentCompletion` rows with it. Otherwise progress keeps crediting the course the lesson left. |

They are signals rather than service calls because a `Teacher` and a
`Content` are each written from `AdminTeamViewSet` / `AdminContentViewSet`
(both `ModelViewSet`s, so the write is `serializer.save()`), the Django
admin, the seed command and the shell. There is no shared chokepoint to hang
a service call on, and the README's own rule says not to convert those
viewsets away just to create one.

**What must never become a signal.** Confirming a payment grants course
access; placing an order reserves stock. Those are business operations, and
they belong in `services.py` where they are explicit, ordered, and inside one
transaction you can see. A reader of `confirm_payment` can follow every write
it makes; the moment that enrolment happens via a `post_save` on `Payment`,
they cannot. The rule of thumb: **signals keep data true, services decide
what happens.**

Two mechanics worth knowing before adding a third:

- **`created` is checked first.** These receivers return immediately on
  insert; there is nothing to reconcile with a row that has just appeared,
  and skipping it keeps bulk seeding cheap.
- **`pre_save` is how you get the old value.** `faculty` cannot tell an
  inherited field from a per-course override -- both live in the same column
  -- so it stashes the pre-change values in `pre_save` and, in `post_save`,
  updates only the rows still holding the old one.

### Where a rule belongs

Two rules that look similar live in different layers, and the split is worth
stating because it is easy to get backwards:

- *"`quantity` must be a whole number ≥ 1"* is *shape* — the serializer.
- *"there are only 2 left in stock"* is *state* — the service, because the
  answer depends on the database and can change between the check and the
  write. Checks like that must run inside the same transaction as the write
  they guard, which is only possible in the service.

---

## 2. Directory layout

```
config/                 configuration only -- never app code
  settings/{base,local,production}.py
  urls.py               mounts every app under /api/v1/

apps/<app>/
  models.py             schema
  managers.py           custom QuerySets/Managers        (add when needed)
  services.py           state changes                    (add when needed)
  selectors.py          shared/cross-app reads           (add when needed)
  admin.py
  apps.py
  tests.py
  signals.py            reactions to model saves         (add when needed)
  api/
    urls.py             version dispatch
    v1/
      urls.py           the actual endpoint paths
      views.py          HTTP layer
      serializers.py    request + response serializers
      filters.py        django-filter FilterSets         (add when needed)
```

`api/v1/` is a folder, not a URL kwarg: a future `v2` is a copy of the folder
plus one line in `api/urls.py`, leaving `v1` untouched.

Only `models.py`, `admin.py`, `apps.py` and the `api/` package are mandatory.
Create the rest when the app actually needs them.

### The apps

| App | Owns |
|---|---|
| `core` | Infrastructure only, and the one app with **no domain models**. See "Inside core" below. |
| `identity` | `User`, `OTP`. Phone+OTP and password auth, admin user CRUD. |
| `faculty` | `Teacher`, `CourseInstructor`. |
| `courses` | `Course`, `CourseCategory`, `CoursePrice`, `Coupon`, `Routine`, the `Section`/`Content` tree, `Enrollment`, `CourseMaterial`. |
| `assessment` | `Exam`, `QuestionBank`, `Question`, `ExamAttempt`. |
| `billing` | `Order`, `Payment`, and the admin dashboard aggregates. |
| `store` | `Product`, `CartItem`. |
| `content` | `Notice`, `Page`, `Testimonial`, `Advertisement`, `EBook`, the `/home` aggregate. |
| `support` | `ContactMessage` — the staff inbox behind the contact form. |

### Inside `core`

`core` is the only app that is not a domain, so it is worth knowing its
shape before adding to it:

```
apps/core/
  api/                  DRF plumbing every app imports
    authentication.py   Bearer token auth
    exception_handler.py the {message, errors} envelope
    fields.py           MediaField ({id, link})
    pagination.py       the {data, links, meta} paginator
    permissions.py      IsAdminRole
    responses.py        response shapes more than one app returns
    throttling.py       the auth rate limits
    viewsets.py         AdminModelViewSet + the shared view mixins
    v1/                 core's own endpoints (uploads, SMS balance)
  services/             pluggable SMS backends
  tests/                the cross-cutting guards (see below)
  management/commands/  seed_demo, reslug, dump_url_contract
  models.py             TimestampModel, OrderedModel (both abstract)
  middleware.py         the ?_method= override
  slugs.py              Bengali-aware slugify
  spreadsheets.py       .xlsx reading for the two importers
  url_contract.py       the served-path snapshot
  utils.py              get_logger, truncate, scrub_headers
```

The loose modules at the top are each one focused thing, and are named for
it. Resist folding them into a `utils/` package: `apps.core.slugs` reads
better at an import site than `apps.core.utils.slugs`, and a grab-bag
directory is where unrelated code goes to hide.

`tests/` is a package rather than four `test_*.py` files at the top level
because those files are over a thousand lines between them -- more than a
third of `core` -- and sorted alphabetically they buried the modules that are
actually shared infrastructure. `tests/base.py` holds `ThrottledAPITestCase`
for other apps to subclass; it is named `base` so the `test*.py` discovery
pattern skips it.

### Dependency direction

**Apps depend downward only.** `billing` and `store` depend on `courses`;
`courses` must never import from them. Money knows about the catalogue; the
catalogue does not know about money.

Where a lower app genuinely needs a fact from a higher one, it declares a hole
and the higher app fills it at startup. The one existing case: the course
payload carries `has_order`, which is a billing fact.
`apps/courses/selectors.py` declares `ordered_course_ids_provider = None`, and
`BillingConfig.ready()` (`apps/billing/apps.py`) injects the real query from
`apps/billing/selectors.py`. If billing were removed the field degrades to
`False` instead of raising.

Use this pattern rather than a function-local `import` to dodge a cycle. A
lazy import inside a method hides the cycle; it does not remove it.

---

## 3. Naming

| Thing | Convention | Example |
|---|---|---|
| Model | PascalCase, singular | `ExamAttempt`, `CoursePrice` |
| View | `<Subject><Action>APIView` | `PublicCourseListAPIView`, `AdminPaymentUpdateAPIView` |
| Shared view parent | `Base` prefix | `BaseExamAPIView` |
| Input serializer | `<Subject>RequestSerializer` | `OrderCreateRequestSerializer` |
| Output/CRUD serializer | `<Model>Serializer` | `CourseListSerializer` |
| Service function | imperative verb, keyword-only args | `grant_course_access(*, user, course, ...)` |
| QuerySet | `<Model>QuerySet` in `managers.py` | `OrderQuerySet`, `UserQuerySet` |
| Selector function | noun phrase | `ordered_course_ids(user, course_ids)` |
| URL path segment | kebab-case, trailing slash | `course-materials/` |
| Route `name=` | snake_case | `admin_payment_update` |

Reverse names are `api:<app>:v1:<name>` — always reverse by name in tests,
never hardcode a path.

Prefix a view with `My`/`Current` when it is scoped to `request.user`
(`MyCourseListAPIView`, `CurrentUserAPIView`).

---

## 4. Query cost

This is a read-heavy API over nested data, so query count is a first-class
concern and is enforced by tests.

- Serializers needing per-row aggregates take them from a **batch in
  `context`**, falling back to a per-object query when it is absent. The same
  serializer is then cheap in a list and still correct for a single object.
  The three batchers are `build_course_stats`, `build_section_tree` and
  `build_category_children`, all in `apps/courses/api/v1/serializers.py`. A
  view serializing many rows must pass the matching one.
- Anything recursive (the section tree, the category tree) is fetched whole
  and grouped in Python. Never query per node.
- Every paginated list needs a deterministic `order_by`. Without one, page
  boundaries are undefined and rows can repeat or vanish between pages.
- Prefer a manager method (`Course.objects.active()`) over repeating a
  `filter()`; it is the cheapest place to later add an index hint or an
  annotation for everyone at once.

---

## 5. The three guards

These encode the contract with two shipped frontends. They fail loudly by
design. **If one fails, the change is wrong — not the test.**

| Guard | Pins | Regenerate |
|---|---|---|
| `apps/core/url_contract.txt` | Every served path (94). | `manage.py dump_url_contract`, only when a path change is intended. |
| `apps/core/tests/test_response_shapes.py` | Response *bodies* — exact key lists **and key order**, since DRF emits keys in `Meta.fields` order and both frontends destructure these payloads. | Never casually. |
| `apps/core/tests/test_query_budget.py` | Response *cost*. Each endpoint asserts a query ceiling, and `ScaledQueryBudgetTests` repeats every assertion against twice the data — identical counts at both sizes is what proves an endpoint is flat rather than merely small today. | Raise a ceiling only deliberately, with a reason. |

### Wire conventions these protect

- List endpoints return Laravel's envelope: `{data, links, meta}`. **Never**
  DRF's `{count, next, previous, results}` — both frontends read `data`,
  `meta.total`, `meta.from`, `meta.to` and `meta.last_page`, so falling back
  to the DRF default renders every list screen empty.
- Validation errors are **422** with `{message, errors: {field: [msg, ...]}}`.
  Everything else is `{message}`. Views never build these — they `raise` a DRF
  exception and `apps/core/api/exception_handler.py` renders it.
- **401 force-logs-out all three clients.** Never use it for an authorization
  failure; that is 403.
- Media fields serialize as `{id, link}` (except `EBook.preview`, which is
  bare). Decimals are strings on the wire.
- Whether a given endpoint wraps its payload in `{data: ...}` or returns it
  bare is **per-endpoint and currently inconsistent**. It is frozen contract:
  changing either direction breaks a specific screen.

---

## 6. Decisions worth knowing

Things that look wrong until you know why, so nobody "fixes" them twice.

| Decision | Why |
|---|---|
| URLs are `/api/v1/<resource>/`, not `/api/<app>/v1/<resource>/` | The API must not advertise which Django app owns what, so models can move between apps without breaking a client — which is exactly what a later re-decomposition did. |
| Timestamps are `created_at` / `updated_at` | Exposed in serializers and read by both frontends. |
| `verbose_name=_()` is omitted on model fields | ~260 fields and a migration in every app, for no functional gain. |
| ~20 `ModelViewSet`s are kept rather than converted to `APIView` | They are router-generated CRUD; converting loses that for nothing. |
| Errors are `{message, errors}`, not DRF's `{detail}` | Both frontends parse the Laravel-style envelope. |
| `meta.links` is a *window* around the current page, not one entry per page | Laravel emits one per page: at 50k rows that is thousands of link objects and hundreds of KB of JSON on every request. Both frontends paginate off `meta.last_page` and read neither the count nor the contents of `meta.links`. Widen it via `page_link_window` if a client ever needs more. |
| `Bearer`, not DRF's default `Token`, is the auth keyword | Matches what both frontends already send. |

---

## 7. The generated schema

`drf-spectacular` builds `/api/schema/` from the serializers, and
`/api/docs/` renders it. It generates clean -- no errors, no warnings -- and
that is worth defending, because every warning is a place the documentation
has quietly stopped describing the code.

What keeps it clean:

- **Declare the request.** A plain `APIView` cannot be introspected, so each
  handler carries `@extend_schema(request=..., responses=...)`. If you find
  yourself unable to name a request serializer, that is usually a sign the
  handler is still reading `request.data` directly.
- **Type the method fields.** A `SerializerMethodField` needs a return
  annotation (`def get_video_count(self, obj) -> int:`) or it is documented
  as a string.
- **Custom fields describe themselves.** `MediaField` and
  `DetailsJsonStringField` set `_spectacular_annotation` so the `{id, link}`
  and JSON-string shapes appear correctly rather than as bare strings.
- **Querysets that depend on the request** use `SchemaSafeQuerysetMixin`
  (`apps/core/api/viewsets.py`). The generator calls `get_queryset()` with an
  anonymous user and no URL kwargs; without the guard those views raise and
  drop out of the schema.

---

## 8. Adding an endpoint

1. Add the path to `apps/<app>/api/v1/urls.py` with a snake_case `name=`.
2. Write the input serializer first. If you find yourself reaching for
   `request.data.get(...)` in a view, the serializer is missing.
3. Put the state change in `services.py` as a keyword-only function, and give
   it `@transaction.atomic` if it writes more than one row.
4. Keep the view under ~15 lines.
5. Add a test asserting the response body, and reverse the URL by name.
6. Run `manage.py test`, `ruff check .`, and
   `manage.py spectacular --file /dev/null`. All three must be clean.
7. If you intentionally changed a path, regenerate the URL contract.
