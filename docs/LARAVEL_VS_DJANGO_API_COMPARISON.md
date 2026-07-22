# Laravel → Django API Comparison Report

**Project:** ICT with Rahad Sir platform
**Old backend:** Laravel API at `https://rahat-ict.nextlms.net/api` (inferred/reverse-engineered from `ictwithrahadsir-client` and `ictwithrahadsir-admin` source code)
**New backend:** Django + DRF at `ictwithrahadsir-api` (this repo)
**Last updated:** 2026-07-21

---

## How to read this report

Each endpoint group below shows:

- **Route** — method + path (same on both backends; both are mounted with no trailing slash)
- **Request body** — what the frontend sends, old vs new
- **Response body** — what comes back, old vs new
- **Status** — one of:
  - ✅ **Match** — verified identical (either by reading the frontend's real page source, or by hitting the live Django server and comparing)
  - 🔧 **Fixed** — was mismatched in the first pass, has since been corrected and re-verified live
  - ⚠️ **Unverified** — best-effort reconstruction from an earlier reverse-engineering pass; not independently re-checked against a live capture or the frontend's actual per-page source in this round
  - ❌ **Known gap** — confirmed different, not yet fixed

Confidence matters here: some of this was checked by literally reading `app/(dashboard)/course/[id]/users/page.tsx` line by line and running real requests against the Django server; some is inferred from an earlier summarization pass. Don't treat the two the same way.

---

## Summary of what changed since the first audit

| Area | First pass | Now |
|---|---|---|
| Foreign key field naming (`course_id` vs `course`, etc.) | ❌ broken across ~10 serializers | 🔧 fixed everywhere |
| `Payment.details` response type | ❌ object, frontend does `JSON.parse()` on it | 🔧 fixed — now a JSON string |
| `CoursePrice` model | ❌ flat `course` FK only | 🔧 fixed — real `priceable_type`/`priceable_id` polymorphism |
| Course enrollment (`/admin/course/*`) response shape | ❌ inverted (pivot-wraps-user) | 🔧 fixed — flat user + nested `pivot` |
| Course enrollment write endpoints | ❌ expected `course_id`, frontend sends `slugOrId` | 🔧 fixed — accepts numeric id or slug |
| Everything in §00 (auth), §04 (exams), §08 (dashboard) | ✅ already matched | ✅ still matches |

---

## 01 — Auth & session

### `GET /get-otp?phone=01711000000`

Request: query param only, no body.

Response (✅ match):
```json
{
  "user_exist": false,
  "password_exist": false,
  "message": "OTP sent."
}
```

### `POST /verify-otp`

Request:
```json
{ "phone": "01711000000", "otp": "405502" }
```

Response — existing user (✅ match):
```json
{
  "token": "f7aac706ab3f4a069c68337f4b0781caf15abb94",
  "user": { "id": 2, "name": "...", "phone": "01711000000", "...": "..." }
}
```

Response — new user, no account yet (✅ match):
```json
{ "token": "f7aac706ab3f4a069c68337f4b0781caf15abb94", "user": null }
```

### `POST /register`

Request:
```json
{
  "name": "Test Student",
  "phone": "01711000000",
  "institute": "Dhaka College",
  "educational_session": "2024-25",
  "password": "StrongPass123",
  "password_confirmation": "StrongPass123"
}
```

Response (✅ match, verified live):
```json
{
  "token": "b1172b27c81479e11c7a27a991be0022c05e6b36",
  "user": {
    "id": 1,
    "name": "Test Student",
    "email": null,
    "phone": "01711000000",
    "guardian_phone": null,
    "institution": "Dhaka College",
    "educational_session": "2024-25",
    "device_id": null,
    "fcm_token": null,
    "role": "student",
    "image": null,
    "email_verified_at": null,
    "phone_verified_at": "2026-07-21T11:22:13.403450+06:00",
    "date_joined": "2026-07-21T11:22:13.388792+06:00"
  }
}
```
Django adds `date_joined` (extra, harmless). Everything else matches the client's `User` type field-for-field.

### `POST /login` (shared by both client and admin)

Request — client (phone):
```json
{ "phone": "01711000000", "password": "StrongPass123" }
```
Request — admin (email):
```json
{ "email": "admin@ictwithrahadsir.com", "password": "ChangeMe123!" }
```
Response (✅ match, both forms verified live): same `{token, user}` shape as register.

### `POST /forget-password`
Request: `{ "phone": "01711000000" }` → Response: `{ "message": "OTP sent." }` — ✅ match.

### `POST /password-reset`
Request:
```json
{
  "phone": "01711000000",
  "otp": "405502",
  "password": "NewPass123",
  "password_confirmation": "NewPass123"
}
```
Response: `{ "token": "...", "message": "Password has been reset." }` — ✅ match (Laravel typed `token`/`message` as optional; Django always includes both, a superset).

### `POST /logout`, `POST /admin/logout`
No body (Bearer token only) → `{ "ok": true }` — ✅ match.

### `GET /user`
Response: `{ "data": { ...same User shape as above... } }` — ✅ match.

**Known gap (⚠️ unverified):** the original `User` type carries an optional `pivot` sub-object when a user is embedded inside a course-enrollment context. Django's base `UserSerializer` never adds this — but this specific case is now handled correctly by the dedicated `CourseUserSerializer` used on the enrollment endpoints (see §05), so it isn't a live problem, just a note that the base serializer alone isn't a drop-in replacement for every embedding context.

---

## 02 — Homepage aggregate — `GET /home`

No request body. Response, side by side:

**Old (Laravel, reconstructed from the client's `HomeResponse` type — ⚠️ unverified nested shapes):**
```json
{
  "courses": [ /* Course[] */ ],
  "courseCategories": [ /* CourseCategory[], nesting field ambiguous */ ],
  "advertisement": [
    { "id": 1, "title": "...", "subtitle": "...", "image": "...", "link": "..." }
  ],
  "testimonials": [ /* ... */ ],
  "counters": [
    { "id": 1, "key": "homeCourseCounter", "value": 120, "slug": "..." }
  ],
  "suceesstorycounter": 500,
  "instructors": [ /* ... */ ],
  "bannerImage": { "id": 1, "link": "https://..." }
}
```

**New (Django, verified live):**
```json
{
  "courses": [],
  "courseCategories": [],
  "advertisement": [],
  "testimonials": [],
  "counters": {},
  "suceesstorycounter": 0,
  "instructors": [],
  "bannerImage": null
}
```

| Key | Status |
|---|---|
| `courses`, `testimonials`, `instructors`, `suceesstorycounter` (including the kept misspelling) | ✅ match |
| `advertisement` | ❌ known gap — Django's `Advertisement` model uses `description`+`type` fields, not the original's `subtitle` |
| `counters` | ❌ known gap — Django returns a flat `{key: value}` dict, not `Counter[]` objects with `{id, key, value, slug}` |
| `bannerImage` | ❌ known gap — Django returns a full CMS `Page` object, likely should be a bare `{id, link}` media object |
| `courseCategories` | ⚠️ unverified — nesting field name (`children` vs `course_categories`) unconfirmed |

---

## 03 — Public course catalog

### `GET /courses?page=&per_page=&is_online=&category_slug=`

Response envelope (✅ match — Laravel's standard paginator shape):
```json
{
  "data": [ /* Course[] */ ],
  "links": { "first": "...", "last": "...", "prev": null, "next": null },
  "meta": {
    "current_page": 1, "from": 1, "last_page": 1,
    "path": "...", "per_page": 15, "to": 1, "total": 1,
    "links": [ { "url": null, "label": "&laquo; Previous", "active": false }, "..." ]
  }
}
```

One `Course` item (verified live):
```json
{
  "id": 1,
  "title": "Full HSC ICT Course",
  "slug": "full-hsc-ict-course",
  "subtitle": "Complete syllabus",
  "duration": "6 months",
  "is_online": true,
  "active": true,
  "featured": false,
  "fake_user_count": 0,
  "video_count": 1,
  "class_count": 2,
  "exam_count": 1,
  "note_count": 0,
  "link_count": 0,
  "live_count": 0,
  "image": null,
  "price": { "id": 1, "priceable_type": "course", "priceable_id": 1, "title": "Full Course", "amount": "1500.00", "...": "..." },
  "categories": [1],
  "instructors": [ { "id": 1, "name": "Rahad Sir", "designation": "Lead Instructor", "...": "..." } ],
  "subscription_status": { "status": "active", "valid_till": null, "payment_type": "paid" },
  "has_order": true,
  "users_count": 1
}
```

| Field | Status |
|---|---|
| Pagination envelope, all `*_count` fields present in Laravel except audio/online/offline | ✅ match |
| `audio_count`, `online_count`, `offline_count` | ❌ known gap — not modeled in Django (no "audio" content type exists) |
| `categories` | ⚠️ unverified — Django returns bare id array `[1]`; original likely nests full category objects for badge rendering |
| `routines` | ❌ known gap — present in Django only on course *detail*, not on list items (Laravel's list-level `Course` type includes it) |
| `price`, `instructors`, `subscription_status`, `has_order`, `users_count` | ✅ match |

### `GET /courses/{slug}` — adds on top of the list shape:

```json
{
  "course_details": {
    "description": "...",
    "features": [],
    "video": null,
    "pdf_link": null
  },
  "prices": [ { "id": 1, "priceable_type": "course", "priceable_id": 1, "...": "..." } ],
  "sections": [
    {
      "id": 1,
      "course_id": 1,
      "section_id": null,
      "title": "Chapter 1",
      "slug": "1-chapter-1",
      "order": 0,
      "active": true,
      "contents": [
        { "id": 1, "title": "Intro Video", "slug": "intro-video", "type": "video", "variant": "New", "paid": false, "available_from": null, "order": 0 }
      ],
      "sub_sections": []
    }
  ],
  "routines": []
}
```
`course_details` keys match exactly. `sections`/`contents` structure matches (`✅`), though see the note below about lesson-list richness.

**⚠️ Unverified ambiguity:** inside `contents`, Django deliberately returns a slim shape (id/title/slug/type/paid/etc., no `video`/`pdf`/`exam` payload) — a lesson viewer must call `GET /content/{slug}` separately per lesson. Whether the original Laravel API eagerly embedded full lesson payloads directly in this tree is genuinely unclear from the source and worth confirming against the client's actual lesson-list rendering code before trusting either way.

---

## 04 — Lesson content — `GET /content/{slug}`

Response (✅ match, verified live):
```json
{
  "id": 1,
  "title": "Intro Video",
  "slug": "intro-video",
  "type": "video",
  "paid": false,
  "course_id": 1,
  "section_id": 1,
  "available_from": null,
  "video": {
    "id": 1, "title": "Intro Video", "source": "youtube",
    "link": "https://youtube.com/watch?v=abc",
    "description": "", "embedded": true, "cipher": false
  },
  "pdf": null,
  "exam": null,
  "link": null
}
```

Access gate when the student isn't subscribed (✅ match, verified live):
```
HTTP 403
{ "message": "Not subscribed" }
```

`course_id`/`section_id` naming was the original mismatch here (Django used to send bare `course`/`section`) — 🔧 **fixed**.

---

## 05 — Course enrollment (admin) — 🔧 fully rebuilt

### `GET /admin/course/{id}/users`

**Old shape the admin page actually reads (`app/(dashboard)/course/[id]/users/page.tsx`):**
```ts
interface CourseUser {
  id: number; name: string; email: string | null; phone: string | null; role: string;
  pivot: { course_id: number; user_id: number; valid_till: string | null; payment_type: string; created_at: string; updated_at: string; };
}
```

**New Django response (🔧 fixed, verified live):**
```json
{
  "data": [
    {
      "id": 2,
      "name": "Enrolled Student",
      "email": null,
      "phone": "01722000000",
      "role": "student",
      "pivot": {
        "course_id": 1,
        "user_id": 2,
        "valid_till": "2027-01-17T07:40:12.698930Z",
        "payment_type": "paid",
        "created_at": "2026-07-21T07:40:12.699512Z",
        "updated_at": "2026-07-21T07:40:12.699528Z"
      }
    }
  ],
  "links": { "...": "..." },
  "meta": { "...": "..." }
}
```
Was previously an inverted `{id, course, user: {...}, valid_till, payment_type}` shape — 🔧 **fixed**, now matches exactly.

### `POST /admin/course/user-attach`

Request (exact payload the admin sends):
```json
{
  "user": { "title": "Enrolled Student -- null -- 01722000000", "id": 2 },
  "price_id": 1,
  "slugOrId": "full-hsc-ict-course",
  "user_id": 2
}
```
Note: no `course_id`, no `valid_till`, no `payment_type` — those are derived server-side.

Response (🔧 fixed, verified live — same flat+pivot shape as the list):
```json
{
  "id": 2, "name": "Enrolled Student", "email": null, "phone": "01722000000", "role": "student",
  "pivot": {
    "course_id": 1, "user_id": 2,
    "valid_till": "2027-01-17T07:40:12.698930Z",
    "payment_type": "paid",
    "created_at": "2026-07-21T07:40:12.699512Z", "updated_at": "2026-07-21T07:40:12.699528Z"
  }
}
```
`valid_till` was computed from the selected price's `validity_duration` (180 days from now); `payment_type` was set to `"paid"` because the price's `amount` was non-zero. Both previously had to be supplied by the caller (they aren't) — 🔧 **fixed**.

### `POST /admin/course/user-update`
Request: `{ "user_id": 2, "slugOrId": "1", "valid_till": "2027-06-01 00:00:00" }` — `slugOrId` accepts either the numeric id or the slug (both tested live) — 🔧 **fixed** (was `course_id`-only before).

### `POST /admin/course/user-remove`
Request: `{ "user_id": 2, "slugOrId": "full-hsc-ict-course" }` → `{ "ok": true }` — 🔧 **fixed**.

---

## 06 — Price & coupon (admin) — 🔧 fixed

### `POST /admin/price`

**Real admin payload:**
```json
{
  "priceable_type": "course",
  "priceable_id": 1,
  "title": "Full Course",
  "amount": "1500.00",
  "discount": "0",
  "type": "full",
  "validity_type": "relative",
  "validity_duration": 180
}
```

**New Django response (🔧 fixed, verified live):**
```json
{
  "id": 1,
  "priceable_type": "course",
  "priceable_id": 1,
  "title": "Full Course",
  "amount": "1500.00",
  "discount": "0.00",
  "discount_till": null,
  "type": "full",
  "validity_type": "relative",
  "validity_time": null,
  "validity_duration": 180
}
```
The model used to only support a flat `course` foreign key; it now genuinely supports polymorphic attachment (`priceable_type`/`priceable_id`), matching the admin UI's design (intended to eventually price non-course items too) — 🔧 **fixed**.

List filtering: `GET /admin/price?priceable_type=course&course_id=1` — ✅ match (query param names were already correct before this fix; only the write/read body shape needed the change).

### `POST /admin/coupon`
Request: `{ "price_id": 1, "code": "SAVE10", "discount": "10", "discount_type": "percent", "valid_till": null }` — field renamed from `price` → `price_id` — 🔧 **fixed**.

---

## 07 — Instructor / section / content builder (admin) — 🔧 fixed

All confirmed against the admin page's actual mutation payloads.

### `POST /admin/instructor`
Request (multipart FormData): `course_id, user_id, name, email, phone, designation, institute, commission, image?`
Response: same fields back, `course_id`/`user_id` now correctly named (was `course`/`user`) — 🔧 **fixed**, verified live.

### `POST /admin/routine`
Request: `{ "course_id": 1, "title": "...", "link": "..." }` — 🔧 **fixed**.

### `POST /admin/section`
Request: `{ "course_id": 1, "title": "Chapter 1" }` (optionally `section_id` for a sub-section)
Response (verified live):
```json
{ "id": 1, "course_id": 1, "section_id": null, "title": "Chapter 1", "slug": "1-chapter-1", "order": 0, "active": true }
```

### `POST /admin/content`
Request: `{ "course_id": 1, "section_id": 1, "title": "Intro Video", "type": "video", "video_link": "...", "paid": false }`
Response includes `course_id`, `section_id`, `exam_store_id` (all renamed from bare `course`/`section`/`exam_store`) — 🔧 **fixed**, verified live.

### `GET /admin/content/toggle/{id}?action=active|paid`
Unconventional `GET` for a state toggle — kept as-is, matches the admin UI exactly — ✅ match.

### Multipart "update" trick
`POST /admin/{resource}/{id}?_method=PUT` (or `PATCH`) — handled by `MethodOverrideMiddleware`, which rewrites the request method before DRF routes it — ✅ match.

---

## 08 — MCQ bank & exam-taking

### `POST /admin/mcq`
Request (multipart): `{ mcq_store_id, question, a, b, c, d, e?, answer, explanation?, question_image?, answer_image? }`
Response field renamed `mcq_store` → `mcq_store_id` — 🔧 **fixed**, verified live.

### `GET /exams/{id}`
Response (✅ match, verified live):
```json
{
  "id": 2, "title": "Chapter 1 Exam", "duration": 10, "total_marks": 1, "pass_marks": 1,
  "positive_marks": 1.0, "negative_marks": 0.25, "start_time": null, "end_time": null, "result_publish_time": null,
  "question": {
    "id": 2, "exam_id": 2,
    "body": {
      "sections": [
        { "title": "Chapter 1 MCQs", "required": true, "questions": [
          { "id": 1, "question": "1+1=?", "a": "1", "b": "2", "c": "3", "d": "4", "e": null, "answer": "b", "explanation": "", "source": { "year": "", "board": "", "topic": "", "chapter": "", "college": "", "subject": "" } }
        ] }
      ],
      "max_sections": 1
    }
  },
  "result": null
}
```

### `POST /exams/{id}` (submit)
Request:
```json
{ "sections": [ { "title": "Chapter 1 MCQs", "answers": [ { "mcq_id": 1, "user_answer": "b" } ] } ], "duration": 42 }
```
Response (✅ match, verified live — scoring confirmed correct: +1 for the right answer):
```json
{ "marks": 1.0, "positive_marks": 1.0, "negative_marks": 0.25, "duration": 42, "submitted": true, "answers": [ "..." ] }
```

### `GET /ranking/{id}`
Response (✅ match, verified live):
```json
{
  "exam_title": "Chapter 1 Exam",
  "user_rank": 1,
  "user_result": { "id": 1, "user": { "id": 1, "name": "Test Student", "institution": "Dhaka College", "image": null }, "duration": 42, "marks": "1.00" },
  "rankings": [ "...same shape..." ]
}
```

---

## 09 — Orders & payment — 🔧 fixed

### `POST /order`
Request: `{ "course_id": 1, "price_id": 1 }` — ✅ match (was already correct).
Response (verified live):
```json
{
  "id": 1,
  "order": {
    "id": 1, "user_id": 2, "course_id": 1, "product_id": null, "price_id": 1,
    "quantity": 1, "item_title": "Full HSC ICT Course", "price_title": "Full Course",
    "amount": "1500.00", "total": "1500.00", "status": "pending", "created_at": "..."
  }
}
```
`user_id` was missing entirely before this fix (Order had no `user` field exposed at all) — 🔧 **fixed**.

### `POST /payment`
Request:
```json
{
  "order_id": 1, "amount": 1500, "transaction_id": "TXN999",
  "details": "{\"vendor\":\"bkash\",\"sent_from\":\"01711000000\",\"sent_to\":\"01711778602\"}"
}
```
Response (🔧 fixed, verified live):
```json
{
  "id": 1, "order_id": 1, "amount": "1500.00", "transaction_id": "TXN999",
  "details": "{\"vendor\": \"bkash\", \"sent_from\": \"01711000000\", \"sent_to\": \"01711778602\"}",
  "status": "pending", "created_at": "..."
}
```
`details` used to serialize as a nested JSON *object*; the admin panel calls `JSON.parse(details)` on it, which throws on a non-string. Now correctly returns a JSON string — 🔧 **fixed**, this was a hard runtime break before.

### `GET /admin/payment`
Response item (🔧 fixed, verified live):
```json
{
  "id": 1, "order_id": 1,
  "order": { "id": 1, "user_id": 2, "course_id": 1, "...": "..." },
  "user": { "id": 2, "name": "Enrolled Student", "phone": "01722000000" },
  "amount": "1500.00", "transaction_id": "TXN999",
  "details": "{\"vendor\": \"bkash\", \"...\": \"...\"}",
  "status": "pending", "created_at": "..."
}
```
Now includes both the flat `order_id` *and* the nested `order` object simultaneously, matching the admin's real `Payment`/`PaymentOrder` TypeScript interfaces exactly — 🔧 **fixed** (previously only had the nested object).

### `PATCH /admin/payment/{id}`
Request: `{ "status": "successful" }` → also auto-enrolls the student in the course (verified live) — ✅ match.

---

## 10 — Shop & cart — ⚠️ low confidence, not independently re-verified

No admin page manages `Product` in the current admin UI at all, and the client's cart code looks like early scaffolding. These were implemented to spec from the client's TypeScript types but never confirmed against a live request capture.

```
GET/POST /cart
POST /cart/add-remove          { product_id, action: "increment" | "decrement" }
DELETE /cart/delete/{productId}
POST /free-course-purchase     { course_id }
GET /products                  -- speculative; no frontend equivalent found
GET/POST/PUT/DELETE /admin/product/{slug}  -- speculative; no admin UI consumes this yet
```

---

## 11 — Notices, pages & CMS

| Endpoint | Status |
|---|---|
| `GET /notices`, `GET /notice-category` | ✅ match — confirmed against a real captured `notices_output.json` response, exact pagination envelope |
| `GET /page/{key}`, `PATCH /admin/page/{slug}` | ✅ match |
| `GET/POST/PATCH/DELETE /admin/testimonial` | ✅ match (`ratings`, not `rating`, on both sides deliberately) |
| `GET/POST/PATCH/DELETE /admin/advertisement` | ❌ known gap — `subtitle` (Laravel) vs `description` (Django) |
| `GET/POST/PATCH/DELETE /admin/exclusive-ebook` | ⚠️ unverified |
| `GET /admin/contact`, `GET /admin/toggle-contact/{id}`, `PATCH /admin/contact/{id}` | ⚠️ toggle-read route verified live; reply field name (`reply_message`) not independently re-checked |
| `GET /admin/course-materials` | ✅ match — read-only on both sides |

Example Notice response (✅ match):
```json
{
  "id": 1, "title": "...", "slug": "...", "body": "<p>...</p>",
  "image": { "id": 123456, "link": "https://..." },
  "categories": [1, 2], "created_at": "..."
}
```

---

## 12 — Dashboard & SMS balance — ✅ all match

```json
GET /admin/dashboard
{
  "income": { "thisMonth": 1500.0, "thisYear": 1500.0, "lifeTime": 1500.0 },
  "orders": { "completed": { "thisMonth": 1, "thisYear": 1 }, "incomplete": { "thisMonth": 0, "thisYear": 0 } },
  "totalCounts": { "courses": 1, "students": 1 },
  "studentsRegistered": { "thisMonth": 1, "thisYear": 1 }
}
```
```json
GET /admin/dashboard/sales-overview
{ "months": ["2026-07"], "courseSales": [1] }
```
```json
GET /admin/dashboard/payment-chart
{ "allDays": ["2026-07-21"], "income": [1500.0] }
```
```json
GET /admin/sms-balance
{ "balance": 0, "currency": "BDT" }
```
(SMS balance is stubbed to 0 until a real gateway is configured — see `apps/core/sms.py`.)

---

## Error envelope (both backends, ✅ match)

Validation error (`422`):
```json
{ "message": "The given data was invalid.", "errors": { "password_confirmation": ["Passwords do not match."] } }
```
Auth error (`401`): `{ "message": "Unauthenticated." }`
Not found (`404`): `{ "message": "Not found." }`

---

## Remaining known gaps (not yet fixed)

1. **§02** `/home` — `advertisement.subtitle`, `counters` shape, `bannerImage` shape
2. **§03** Public course `categories` — bare id array vs likely-nested category objects; `routines` missing from list-level Course; `audio_count`/`online_count`/`offline_count` not modeled
3. **§04** Section-tree lesson richness — slim content shape vs possibly-eager full payload (genuinely ambiguous, needs checking against the client's lesson-list component)
4. **§10** Shop/cart/product — entirely unverified against a live capture
5. **§11** Advertisement `subtitle` vs `description`, EBook fields, Contact reply field name

None of these block core admin workflows the way the fixed issues did — they're either cosmetic (extra/renamed fields the frontend may just ignore) or in a feature area (shop) that doesn't appear to be actively used by either shipped frontend yet.
