# Desired Django API Spec (target parity with Laravel)

This is the build-to checklist for `ictwithrahadsir-api` reaching full
carbon-copy parity with the old Laravel backend (`https://rahat-ict.nextlms.net/api`),
consumed by `ictwithrahadsir-client` and `ictwithrahadsir-admin` unchanged.

Status legend: ✅ done and verified · 🔧 implemented but needs a fix to match ·
❓ needs to be checked against a live Laravel capture before trusting the shape below.

Global conventions (already correct, keep as-is):
- No trailing slash on any route (`APPEND_SLASH=False`).
- List endpoints: Laravel pagination envelope `{data, links, meta}`.
- Validation errors: `422 {message, errors: {field: [msg]}}`.
- Auth errors: `401 {message: "Unauthenticated."}`; not found: `404 {message: "Not found."}`.
- Every image/file field serializes as `{id, link}`.
- `/admin/*` requires a token for a `staff`/`admin`/`instructor` user.
- Multipart "update" trick: `POST .../{id}?_method=PUT|PATCH`.

---

## 01 — Auth & session (`apps/accounts`)

| Method & Path | Status | Notes |
|---|---|---|
| `GET /check-phone` | ✅ | |
| `GET /get-otp?phone=` | ✅ | `{user_exist, password_exist, message}` |
| `POST /verify-otp` | ✅ | `{token, user}` or `{token, user: null}` for new numbers |
| `POST /register` | ✅ | |
| `POST /login` (phone or email) | ✅ | shared route for client + admin |
| `POST /forget-password` | ✅ | |
| `POST /password-reset` | ✅ | |
| `POST /logout`, `POST /admin/logout` | ✅ | |
| `GET /user` | ✅ | `{data: User}` |
| `GET /admin/user-search` | ✅ | |
| `POST /admin/user/import` | ✅ | |
| `GET/POST/PATCH/DELETE /admin/user/{id}` | ✅ | |

No action needed here — fully matched already.

---

## 02 — Homepage aggregate (`apps/cms`) — `GET /home` — 🔧 fixed

| Key | Status | Notes |
|---|---|---|
| `courses`, `testimonials`, `instructors` | ✅ | |
| `advertisement` | ✅ | verified against real admin/client source — the client's declared `subtitle` field is never actually read anywhere; admin's own `Advertisement` TS type is `{title, description, link, type, image}`, matching Django exactly. Not a real gap. |
| `counters` | 🔧 fixed | was reading a dead `Counter` model with zero rows. Admin's Pages screen actually manages homepage counters as `Page` rows (`value_type="counter"`, keys `homeCourseCounter`/`homeStudentCounter`/`homeInstructorCounter`). `/home` now sources `counters` from those `Page` rows as `[{id, key, value, slug}]`, `value` as a string (client does `counter.value.includes("+")`). |
| `suceesstorycounter` | 🔧 fixed | derived from the `homeInstructorCounter` Page's value (the one labeled "Success stories" client-side); kept the misspelling. |
| `bannerImage` | 🔧 fixed | now sourced from the `Page` row keyed `homeBannerImage` (`value_type="image"`), serialized as bare `{id, key, image}` — matches client's `HomeResponse.bannerImage` type exactly (`home.bannerImage.image.link`). |
| `courseCategories` | ❓ still open | nesting field name (`children` vs `course_categories`) unconfirmed — `CourseCategorySerializer` already returns `children`, and `course-category.tsx` checks both names, so likely fine but not independently verified live. |

**New migration** `apps/cms/migrations/0003_seed_home_pages.py` seeds the 4 required
`Page` rows — previously the table was empty and the admin's Pages screen had nothing
to edit (there's no create-a-page endpoint by design), so the homepage banner/counters
were unfixable through the admin UI regardless of API shape.

Note: the `Counter` model is now fully orphaned (only touched by Django's own
`/django-admin/`) — not removed yet, flagged for cleanup.

---

## 03 — Public course catalog (`apps/courses`) — 🔧 fixed

### `GET /courses?page=&per_page=&is_online=&category_slug=`

| Field | Status | Notes |
|---|---|---|
| Pagination envelope + all `*_count` fields | ✅ | |
| `audio_count`, `online_count`, `offline_count` | 🔧 fixed | added as stubbed-to-`0` `SerializerMethodField`s — no model concept of these exists yet and neither frontend reads them beyond the type declaration |
| `categories` | 🔧 fixed | new `CourseCategoryBadgeSerializer` (`{id, title, slug, image}`) replaces bare `PrimaryKeyRelatedField`. This was a **live bug**, not just cosmetic: `course-category.tsx`'s fallback filter does `course.categories?.some((cat) => cat.slug === fetchSlug)` — with bare IDs, `cat.slug` was always `undefined`, so that fallback silently never matched. |
| `routines` | 🔧 fixed | moved from detail-only up into the base `CourseListSerializer`, inherited by both list and detail |
| `price`, `instructors`, `subscription_status`, `has_order`, `users_count` | ✅ | |

### `GET /courses/{slug}`
`course_details`, `prices`, `sections`/`contents` tree — ✅ match structurally.

✅ Resolved: the client's lesson page (`my-courses/[courseSlug]/[lessonSlug]/page.tsx`)
explicitly treats the section tree's embedded content as an **SSR fallback only**
(`findContent(...)`, cast `as unknown as ContentDetail`, comment says so directly) while
a separate `LessonContent` component fetches the real payload from `/content/{slug}`.
Django's slim `ContentListSerializer` + separate `GET /content/{slug}` is exactly the
architecture the client expects — no change needed.

### `GET /course-category` — ✅

---

## 04 — Lesson content (`apps/courses`) — `GET /content/{slug}`, `GET /content/{slug}/pdf`

✅ Fully matched, including the `403 {"message": "Not subscribed"}` gate and
`course_id`/`section_id` naming.

---

## 05 — Course enrollment admin (`apps/courses`)

| Method & Path | Status |
|---|---|
| `GET /admin/course/{id}/users` | ✅ flat user + nested `pivot` |
| `POST /admin/course/{id}/users/import` | ✅ |
| `POST /admin/course/user-attach` | ✅ derives `valid_till`/`payment_type` server-side |
| `POST /admin/course/user-update` | ✅ `slugOrId` accepts id or slug |
| `POST /admin/course/user-remove` | ✅ |

Fully matched — no action needed.

---

## 06 — Price & coupon admin (`apps/courses`)

| Method & Path | Status |
|---|---|
| `GET/POST/PATCH/DELETE /admin/price` (polymorphic `priceable_type`/`priceable_id`) | ✅ |
| `GET /admin/price?priceable_type=&course_id=` | ✅ |
| `GET/POST/PATCH/DELETE /admin/coupon` (`price_id` field) | ✅ |

Fully matched.

---

## 07 — Course builder admin (`apps/courses`)

| Method & Path | Status |
|---|---|
| `GET/POST/PATCH/DELETE /admin/course` | ✅ |
| `GET/POST/PATCH/DELETE /admin/course-category` | ✅ |
| `POST /admin/instructor` (multipart) | ✅ |
| `POST /admin/routine` | ✅ |
| `POST /admin/section` | ✅ |
| `POST /admin/content` | ✅ |
| `GET /admin/content/toggle/{id}?action=active\|paid` | ✅ |

Fully matched.

---

## 08 — MCQ bank & exam-taking (`apps/exams`)

| Method & Path | Status |
|---|---|
| `GET/POST/PATCH/DELETE /admin/mcq-store` | ✅ |
| `GET/POST/PATCH/DELETE /admin/mcq` (multipart, `mcq_store_id`) | ✅ |
| `GET /exams/{id}` | ✅ |
| `POST /exams/{id}` (submit) | ✅ scoring verified correct |
| `GET /ranking/{id}` | ✅ |
| `GET /admin/result` | ✅ |

Fully matched.

---

## 09 — Orders & payment (`apps/shop`)

| Method & Path | Status |
|---|---|
| `POST /order` | ✅ includes `user_id` |
| `POST /payment` | ✅ `details` is a JSON **string**, not object |
| `GET /orders` (my orders) | ✅ |
| `GET /admin/payment` | ✅ flat `order_id` + nested `order` |
| `PATCH /admin/payment/{id}` | ✅ auto-enrolls on `status: "successful"` |

Fully matched.

---

## 10 — Shop & cart (`apps/shop`) — low confidence, needs live verification

None of this is confirmed against a real Laravel capture; the admin UI doesn't manage
`Product` at all today, and client cart code looks like early scaffolding.

| Method & Path | Status | Action |
|---|---|---|
| `GET /products` | ❓ | speculative — confirm whether any frontend actually calls this |
| `GET/POST /cart` | ❓ | confirm request/response shape against client cart code |
| `POST /cart/add-remove` | ❓ | confirm `{product_id, action}` payload shape |
| `DELETE /cart/delete/{productId}` | ❓ | |
| `POST /free-course-purchase` | ❓ | confirm `{course_id}` payload |
| `GET/POST/PUT/DELETE /admin/product/{slug}` | ❓ | speculative — no admin UI consumes this yet |

Action: before investing more here, grep both frontends for `/cart`, `/products`,
`/free-course-purchase` call sites and diff actual payloads; this section is
lowest priority since neither shipped frontend appears to use it yet.

---

## 11 — Notices, pages & CMS (`apps/cms`) — 🔧 fixed

| Method & Path | Status | Notes |
|---|---|---|
| `GET /notices`, `GET /notice-category` | ✅ | confirmed against real capture |
| `GET /page/{key}` | ✅ | |
| `PATCH /admin/page/{slug}`, `GET /admin/page` | ✅ | |
| `GET/POST/PATCH/DELETE /admin/testimonial` | ✅ | keep `ratings` (plural) |
| `GET/POST/PATCH/DELETE /admin/advertisement` | ✅ | not a real gap — verified against admin's own `Advertisement` TS type, which matches `description`/`type` exactly (see §02) |
| `GET/POST/PATCH/DELETE /admin/exclusive-ebook` | 🔧 fixed | `preview` was serializing as `{id, link}` via `MediaField`, but admin's `EBook.preview` is typed `string \| null` and the UI calls `.split("/")` on it directly and uses it as an `<a href>` — a real bug (`.split` doesn't exist on an object). Added a `bare=True` option to `MediaField` and used it for `preview` only; `image` stays as `{id, link}`. |
| `GET /admin/contact` | ✅ | |
| `GET /admin/toggle-contact/{id}` | ✅ | verified live |
| `PATCH /admin/contact/{id}` | 🔧 fixed | write path already worked (view reads `reply_message` straight from `request.data`), but the **read side** only exposed `reply`, not `reply_message` — admin's `ReplyModal` prefill and "Reply Status" column both read `contact.reply_message`, which was always `undefined`. The public client's dashboard support view reads `msg.reply` for the same data. Serializer now exposes both `reply` and `reply_message` for the same underlying field. |
| `GET /admin/course-materials` | ✅ | |
| `POST /contact-us` | ✅ | |

---

## 12 — Dashboard & SMS balance (`apps/core`)

| Method & Path | Status |
|---|---|
| `GET /admin/dashboard` | ✅ |
| `GET /admin/dashboard/sales-overview` | ✅ |
| `GET /admin/dashboard/payment-chart` | ✅ |
| `GET /admin/sms-balance` | ✅ (stubbed to 0 until a real SMS gateway is wired) |

Fully matched.

---

## 13 — Team / uploads (`apps/team`, `apps/core`)

| Method & Path | Status |
|---|---|
| `GET/POST/PATCH/DELETE /admin/team` | ✅ |
| `GET /admin/teacher` | ✅ |
| `POST /aws-upload-url` | ✅ |
| `* /media-upload/{name}` | ✅ (local disk fallback) |

Not covered in the original comparison audit (no Laravel reference checked) —
low risk since these are infra/roster endpoints with simple shapes, but worth a
quick confirmation pass if time allows.

---

## Priority order to close remaining gaps

1. ~~**§02 `/home`**~~ — ✅ done: counters/bannerImage now sourced from seeded `Page` rows instead of the dead `Counter` model; advertisement gap was a false alarm.
2. ~~**§03 course list**~~ — ✅ done: `categories` nested with working `.slug`, `routines` on list items, stub `audio/online/offline_count`.
3. ~~**§03 lesson-list richness**~~ — ✅ resolved: client only wants the slim tree + `/content/{slug}` lookup; no change needed.
4. ~~**§11 EBook/Contact**~~ — ✅ done: `EBook.preview` now a bare string; `ContactMessage` exposes both `reply` and `reply_message`.
5. **Cleanup**: decide whether to remove the now-fully-orphaned `Counter` model (see §02).
6. **§01 known gap** — `UserSerializer`'s `pivot` sub-object note (low priority, already handled correctly by `CourseUserSerializer` on the enrollment endpoints that actually need it).
7. **§02 courseCategories nesting** — low-confidence remaining item; would need a live capture or deeper client trace to fully close.
8. **§10 Shop/cart** — lowest priority; confirm it's even used before investing further.
