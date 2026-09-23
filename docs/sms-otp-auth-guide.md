# SMS OTP + Password Auth — Implementation Guide

How Shomadhan sends verification SMS, verifies mobile numbers, and resets passwords.
Written as a portable recipe: every piece below can be lifted into another Django/DRF
project with only the names changed.

**Core idea:** SMS costs money, so OTP is *not* the login mechanism. Login is
password-based. An OTP is spent **exactly once per lifecycle event** — first signup,
a legacy user setting their first password, and a forgot-password reset. Everyday
returning logins send zero SMS.

---

## 1. Architecture at a glance

```
                        POST /auth/start  { mobile }
                                 │
                 ┌───────────────┴────────────────┐
       has usable password?                 no password yet
                 │                               │  (new user OR legacy OTP-only user)
        {"next": "password"}              send SMS → {"next": "otp"}
                 │                               │
        POST /auth/login                 POST /auth/otp/verify  { mobile, code }
        { mobile, password }                     │
                 │                        tokens + user + setup_token
             tokens + user                       │
                                          POST /auth/set-password
                                          { setup_token, new_password }
                                                 │
                                            tokens + user

Forgot password:  POST /auth/password/reset  →  /auth/otp/verify  →  /auth/set-password
                  (reset is just a named alias of /auth/otp/request)
```

Three moving parts:

| Part | File | Responsibility |
|------|------|----------------|
| `OTPRequest` model | `users/models.py` | One row per dispatched code. Stores a **hash**, never the code. |
| Service layer | `users/services.py` | `send_otp` / `verify_otp` / `_send_sms` / setup-token helpers. All DB + SMS work. |
| Views | `users/views.py` | Thin: validate → call service → serialize. No logic. |

**The single rule that keeps this maintainable:** views never touch `OTPRequest` and
never call the SMS provider. They only call service functions.

---

## 2. The `OTPRequest` model

One row per code sent. The plaintext code exists only inside the SMS body — the DB
holds `sha256(salt + code)`, so a database leak can't be replayed.

```python
import hashlib
import secrets

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class OTPRequest(TimeStampedModel):        # TimeStampedModel = created_at / updated_at
    """A single OTP send attempt — one row per code dispatched to a mobile number."""

    mobile = models.CharField(max_length=20, verbose_name=_("mobile"))

    # Verification
    code_hash = models.CharField(
        max_length=128,
        verbose_name=_("code hash"),
        help_text=_("SHA-256(salt + code). The plaintext code only ever lives in the SMS."),
    )
    salt = models.CharField(max_length=64, verbose_name=_("salt"))

    # Throttling
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name=_("attempts"))
    max_attempts = models.PositiveSmallIntegerField(default=5, verbose_name=_("max attempts"))

    # Lifecycle
    expires_at = models.DateTimeField(verbose_name=_("expires at"))
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name=_("consumed at"))

    request_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name=_("request ip"))

    class Meta:
        # Both rate-limit queries and the "latest unconsumed code" lookup filter
        # on (mobile, created_at) — this index carries all of them.
        indexes = [models.Index(fields=["mobile", "created_at"])]
        verbose_name = _("OTP request")
        verbose_name_plural = _("OTP requests")

    def __str__(self):
        return f"OTP for {self.mobile} at {self.created_at}"

    @classmethod
    def hash_code(cls, code: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}{code}".encode()).hexdigest()

    @classmethod
    def generate_salt(cls) -> str:
        return secrets.token_hex(16)

    def check_code(self, code: str) -> bool:
        return self.code_hash == self.hash_code(code, self.salt)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    @property
    def is_exhausted(self) -> bool:
        return self.attempts >= self.max_attempts
```

### Design notes worth copying

- **No FK to `User`.** The OTP is keyed by mobile *string*, because at first-signup no
  user row exists yet. The user row is created only at OTP-verify time.
- **Three independent kill switches** — `is_expired`, `is_consumed`, `is_exhausted` — read
  as separate properties so the verify path is one readable boolean chain.
- **`consumed_at` is a timestamp, not a bool.** You get single-use enforcement *and* an
  audit trail of when the number was verified, for free.
- **Rows are never updated in place on resend.** Each send inserts a new row; verify
  always reads the newest unconsumed one. That makes the rate-limit count a simple
  `COUNT(*)` over a time window.

---

## 3. SMS dispatch — the provider adapter

The only place the provider is named. Everything else calls `_send_sms(mobile, message)`.

```python
import requests as http_requests
from django.conf import settings


def _send_sms(mobile: str, message: str) -> None:
    if settings.OTP_BACKEND == "bulksmsbd":
        # BulkSMSBD expects the number without a leading '+' (e.g. 8801711111111).
        number = mobile.lstrip("+")
        payload = {
            "api_key": settings.BULKSMSBD_API_KEY,
            "senderid": settings.BULKSMSBD_SENDER_ID,
            "type": "text",
            "number": number,
            "message": message,
        }
        response = http_requests.post(
            "https://bulksmsbd.net/api/smsapi", data=payload, timeout=10
        )
        response.raise_for_status()
    else:
        print(f"\n[OTP] Mobile: {mobile}  Message: {message}\n")
```

The `OTP_BACKEND` string switch (`"console"` vs `"bulksmsbd"`) is the highest-value
15 lines in this whole feature:

- **Local dev and CI cost nothing** — the code is printed to the runserver console. You
  never burn SMS credit debugging a signup flow, and tests need no HTTP mocking.
- **Swapping providers (Twilio, SSLWireless, Alpha Net) is one new `elif` branch.** No
  call site changes.
- `timeout=10` is mandatory — without it a hung provider hangs a gunicorn worker.
- `raise_for_status()` means a provider outage surfaces as a 500 rather than silently
  "sending" nothing. Worth deciding deliberately: for the transactional-OTP case, failing
  loudly is right — the user must know to retry.

> **If you want the request off the hot path**, wrap this in a Celery/RQ task. Shomadhan
> keeps it synchronous because BulkSMSBD responds in <1s and the user is staring at the
> "enter code" screen anyway — an async send would just move the failure somewhere the
> user can't see it.

### Mobile number normalisation

Every OTP lookup keys on the *string*, so `01711111111` and `+8801711111111` must not
produce two different identities. Normalise at the serializer boundary — before any
service, DB row, or SMS ever sees the value:

```python
import re


def normalise_mobile(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("880"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+880{digits[1:]}"
    if len(digits) == 10:
        return f"+880{digits}"
    return f"+{digits}"


class OTPRequestSerializer(serializers.Serializer):
    mobile = serializers.CharField(max_length=20)

    def validate_mobile(self, value):
        return normalise_mobile(value)
```

Every auth serializer (`AuthStart`, `Login`, `OTPRequest`, `OTPVerify`) calls the same
function in `validate_mobile`. Adapt the country prefix for your market.

---

## 4. Send: `send_otp`

```python
import random
import string

from django.utils import timezone
from rest_framework.exceptions import Throttled


def _generate_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def send_otp(mobile: str, request_ip: str | None = None) -> None:
    if settings.DEMO_MOBILE and mobile == settings.DEMO_MOBILE:
        return                                       # reviewer account — never spend SMS

    cutoff = timezone.now() - timezone.timedelta(hours=1)

    mobile_count = OTPRequest.objects.filter(mobile=mobile, created_at__gte=cutoff).count()
    if mobile_count >= settings.OTP_RATE_LIMIT_PER_MOBILE_PER_HOUR:
        raise Throttled(detail="Too many OTP requests for this mobile number.")

    if request_ip:
        ip_count = OTPRequest.objects.filter(request_ip=request_ip, created_at__gte=cutoff).count()
        if ip_count >= settings.OTP_RATE_LIMIT_PER_IP_PER_HOUR:
            raise Throttled(detail="Too many OTP requests from this IP address.")

    code = _generate_code()
    salt = OTPRequest.generate_salt()
    expires_at = timezone.now() + timezone.timedelta(seconds=settings.OTP_EXPIRY_SECONDS)

    OTPRequest.objects.create(
        mobile=mobile,
        code_hash=OTPRequest.hash_code(code, salt),
        salt=salt,
        expires_at=expires_at,
        request_ip=request_ip,
    )

    _send_sms(mobile, f"Your Shomadhan OTP is {code}. Valid for 5 minutes.")
```

### Two-axis rate limiting

This is the part that protects your wallet, and it is deliberately **DB-based, not
cache-based**:

| Axis | Limit | Attack it stops |
|------|-------|-----------------|
| per mobile / hour | 5 | Someone spamming resend on one number (SMS-bombing a victim). |
| per IP / hour | 20 | A script walking a range of numbers to drain your SMS balance. |

DRF's `ScopedRateThrottle` is cache-backed and resets when Redis restarts or is flushed
— fine for login brute-force, **not** fine for something that costs real money per call.
Counting `OTPRequest` rows is durable across restarts and gives you a queryable audit
trail of exactly who burned your credit.

The cost is two `COUNT(*)` queries per send; the `(mobile, created_at)` index makes them
trivial, and OTP send is a low-QPS endpoint by nature.

`raise Throttled(...)` from `rest_framework.exceptions` is what lets a *service* function
produce a correct `429` without the view knowing anything about it.

### The demo-account escape hatch

`DEMO_MOBILE` short-circuits the send entirely, and `verify_otp` accepts a fixed
`DEMO_OTP_CODE`. This exists because **Apple and Google app reviewers cannot receive a
Bangladeshi SMS** — without it, every store submission gets rejected as "unable to sign
in". Set `DEMO_MOBILE=""` in env to disable. Better still, also seed `DEMO_PASSWORD` so
reviewers use the plain password path and touch no OTP code at all.

---

## 5. Verify: `verify_otp`

```python
def verify_otp(mobile: str, code: str) -> bool:
    if settings.DEMO_MOBILE and mobile == settings.DEMO_MOBILE and code == settings.DEMO_OTP_CODE:
        return True

    otp = (
        OTPRequest.objects.filter(mobile=mobile, consumed_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if otp is None:
        return False
    if otp.is_expired or otp.is_consumed or otp.is_exhausted:
        return False

    otp.attempts += 1

    if not otp.check_code(code):
        otp.save(update_fields=["attempts"])       # burn the attempt, stay unconsumed
        return False

    otp.consumed_at = timezone.now()
    otp.save(update_fields=["attempts", "consumed_at"])
    return True
```

Properties to preserve when you port it:

- **Only the newest unconsumed row is checked.** Resending invalidates nothing explicitly,
  but the old code becomes unreachable — the natural behaviour users expect.
- **Wrong code increments `attempts` and saves.** After 5 wrong guesses `is_exhausted`
  locks the row, so a 6-digit code can't be brute-forced (1M space, 5 tries, 5-minute
  window).
- **Success sets `consumed_at`.** Single use, enforced at the row.
- **Returns a bare `bool`.** The caller decides the HTTP shape. Never leak *why* it failed
  (expired vs wrong vs exhausted) — that's an enumeration oracle.

---

## 6. Password setup via a signed `setup_token`

After a successful OTP, the user has *proven number ownership* but has no password yet.
Rather than a second DB table for "verified sessions", use Django's built-in signer —
stateless, self-expiring, no cleanup job:

```python
from django.core import signing

_SETUP_TOKEN_SALT = "shomadhan.users.password-setup"


def issue_setup_token(mobile: str) -> str:
    """Short-lived signed token proving OTP ownership, exchanged at set-password."""
    return signing.dumps({"mobile": mobile}, salt=_SETUP_TOKEN_SALT)


def consume_setup_token(token: str) -> str:
    """Return the mobile bound to a setup token.

    Raises ``signing.BadSignature`` (tampered) or ``signing.SignatureExpired``
    (older than PASSWORD_SETUP_TOKEN_TTL_SECONDS).
    """
    data = signing.loads(
        token,
        salt=_SETUP_TOKEN_SALT,
        max_age=settings.PASSWORD_SETUP_TOKEN_TTL_SECONDS,
    )
    return data["mobile"]


def complete_password_setup(mobile: str, new_password: str) -> User:
    """Create-or-fetch the user for a verified mobile and set their password."""
    user, _ = User.objects.get_or_create(mobile=mobile)
    user.set_password(new_password)
    user.save(update_fields=["password"])
    return user
```

- `signing.dumps` signs with `SECRET_KEY` + a **namespaced salt**, so this token can never
  be replayed against another signer in the app.
- `max_age` gives expiry with no stored state and no cleanup cron. TTL is 10 min — long
  enough to type a password, short enough that a leaked token is worthless.
- `SignatureExpired` subclasses `BadSignature`, so a single `except signing.BadSignature`
  in the view covers both tampering and expiry (and returns the same message — again, no
  oracle).
- `get_or_create` is what makes **one** endpoint serve all three flows: new signup (creates),
  legacy first password (fetches), forgot-password reset (fetches and overwrites).

### The `has_password_set` trap — read this one carefully

```python
def has_password_set(user: User) -> bool:
    """True only when the user has a real, usable password.

    Django's ``has_usable_password()`` treats an empty password string — the
    state of every legacy OTP-only user — as usable, so also require a
    non-empty value. This is what routes those users to set a password.
    """
    return bool(user.password) and user.has_usable_password()
```

If your project ever had OTP-only login, those `User` rows have `password = ""`.
`has_usable_password()` returns **`True`** for an empty string (it only checks for the
`!` unusable-password prefix). Using it bare would route every legacy user to the
password screen with a password they never set — a hard lockout of your entire existing
user base. Always guard with `bool(user.password)`.

---

## 7. The routing service: `start_auth`

One endpoint the client always calls first. The backend — not the app — decides the
next screen, so auth policy can change without shipping a new mobile build.

```python
def start_auth(mobile: str, request_ip: str | None = None) -> dict:
    """Decide the next auth step for a mobile number.

    Returns ``{"next": "password"}`` when the number already has a password
    (no SMS spent). Otherwise sends an OTP and returns ``{"next": "otp"}``.
    """
    if _is_demo(mobile) and settings.DEMO_PASSWORD:
        return {"next": "password"}

    user = User.objects.filter(mobile=mobile).first()
    if user is not None and has_password_set(user):
        return {"next": "password"}

    send_otp(mobile, request_ip=request_ip)
    return {"next": "otp"}
```

```python
def authenticate_with_password(mobile: str, password: str) -> User | None:
    """Return the user for valid mobile + password, else None.

    Callers must not leak which half failed — a single 401 covers both.
    """
    if _is_demo(mobile) and settings.DEMO_PASSWORD and password == settings.DEMO_PASSWORD:
        user, _ = User.objects.get_or_create(mobile=mobile)
        return user

    user = User.objects.filter(mobile=mobile).first()
    if user is None or not has_password_set(user) or not user.is_active:
        return None
    if not user.check_password(password):
        return None
    return user
```

**Known trade-off, accepted deliberately:** `/auth/start` is a user-enumeration oracle —
`{"next": "password"}` reveals the number is registered. Removing it would mean sending
an SMS to every unknown number, which is exactly the cost this design exists to avoid.
The IP rate limit bounds how fast an attacker can enumerate.

---

## 8. Views — thin by construction

```python
class OTPRequestView(GenericAPIView):
    serializer_class = OTPRequestSerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile = serializer.validated_data["mobile"]
        ip = request.META.get("REMOTE_ADDR")
        send_otp(mobile, request_ip=ip)
        return Response({"detail": "OTP sent."}, status=status.HTTP_200_OK)


class PasswordResetRequestView(OTPRequestView):
    """Forgot-password entry point — sends an OTP to start a reset.

    Semantically named alias of /auth/otp/request. The client completes the
    reset with the existing two-step: /auth/otp/verify → /auth/set-password.
    """
```

Forgot-password is **a subclass with no body**. The reset flow needed no new logic —
just a URL the client could call with clear intent. Resist the urge to build a separate
reset-token system; OTP-verify already proves ownership of the number, which is the
same proof a reset requires.

```python
class OTPVerifyView(GenericAPIView):
    serializer_class = OTPVerifySerializer
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile = serializer.validated_data["mobile"]
        code = serializer.validated_data["code"]

        if not verify_otp(mobile, code):
            return Response(
                _INVALID_OTP_RESPONSE,
                status=status.HTTP_400_BAD_REQUEST,
                headers={"Content-Type": "application/problem+json"},
            )

        user, _ = User.objects.get_or_create(mobile=mobile)
        payload = _auth_response(user)
        payload["setup_token"] = issue_setup_token(mobile)
        return Response(payload, status=status.HTTP_200_OK)


class SetPasswordView(GenericAPIView):
    serializer_class = SetPasswordSerializer
    permission_classes = [AllowAny]
    throttle_scope = "set_password"

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            mobile = consume_setup_token(serializer.validated_data["setup_token"])
        except signing.BadSignature:
            return Response(
                _INVALID_SETUP_TOKEN_RESPONSE,
                status=status.HTTP_400_BAD_REQUEST,
                headers={"Content-Type": "application/problem+json"},
            )
        user = complete_password_setup(mobile, serializer.validated_data["new_password"])
        return Response(_auth_response(user), status=status.HTTP_200_OK)
```

Every auth response goes through one helper, so the envelope can never drift:

```python
_ACCESS_TOKEN_LIFETIME_SECONDS = 900  # 15 min


def _auth_response(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
        "token_type": "Bearer",
        "expires_in": _ACCESS_TOKEN_LIFETIME_SECONDS,
        "user": ProfileSerializer(user).data,
    }
```

Errors are RFC 7807 problem documents declared as module constants:

```python
_INVALID_OTP_RESPONSE = {
    "type": "https://shomadhan.io/errors/invalid-otp",
    "title": "Bad request",
    "status": 400,
    "detail": "Invalid or expired OTP.",
}
```

### Password validation lives in the serializer

Wire Django's validators in rather than hand-rolling rules:

```python
class SetPasswordSerializer(serializers.Serializer):
    setup_token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate_new_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value
```

For `ChangePasswordSerializer` (authenticated change), pass `user=` so the
similarity validator works: `validate_password(value, user=self.context["request"].user)`.

---

## 9. Backward compatibility — the migration trick

This project **started** OTP-only and moved to passwords with a live mobile app in the
field. The technique that made it a zero-downtime change:

`/auth/otp/verify` still returns the exact historic envelope — access token, refresh
token, `user` — so **old app builds keep logging in by OTP and never break**. It merely
*adds* a `setup_token` field, which old clients ignore. New builds read
`user.password_set` (a `SerializerMethodField` on the profile calling `has_password_set`)
and route to the set-password screen when it's `false`.

The consequence, stated plainly in the code comments: password setup is
**client-enforced**, not withheld at the token layer. That's an accepted weakening —
the anti-fake-number guarantee still holds, because a fake number can never pass the
OTP in the first place. Once every old build has aged out, you can stop issuing tokens
from verify and make setup mandatory.

**Port this pattern whenever you change an auth contract:** keep the old response shape,
add the new field, flip behaviour on a flag in the payload, remove the old path later.

---

## 10. Settings and env

```python
# config/settings/base.py

# Provider credentials
BULKSMSBD_API_KEY = env("BULKSMSBD_API_KEY", default="")
BULKSMSBD_SENDER_ID = env("BULKSMSBD_SENDER_ID", default="")

# OTP settings
OTP_EXPIRY_SECONDS = 300          # 5 minutes
OTP_MAX_ATTEMPTS = 5
OTP_RATE_LIMIT_PER_MOBILE_PER_HOUR = 5
OTP_RATE_LIMIT_PER_IP_PER_HOUR = 20

# OTP backend (swap to "bulksmsbd" in production)
OTP_BACKEND = env("OTP_BACKEND", default="console")

# Short-lived signed token issued by OTP verify and exchanged for JWTs once the
# user sets a password. Bounds the window between proving number ownership and
# completing setup.
PASSWORD_SETUP_TOKEN_TTL_SECONDS = 600  # 10 minutes

# Demo account for app-store reviewers. Set DEMO_MOBILE="" to disable.
DEMO_MOBILE = env("DEMO_MOBILE", default="+8801700000000")
DEMO_OTP_CODE = env("DEMO_OTP_CODE", default="000000")
DEMO_PASSWORD = env("DEMO_PASSWORD", default="")
```

`config/settings/test.py` pins `OTP_BACKEND = "console"` so the test suite can never
make a real HTTP call, even if someone's `.env` leaks into the test run.

```bash
# .env.example
# OTP backend: "console" (dev) or "bulksmsbd" (prod)
OTP_BACKEND=console
BULKSMSBD_API_KEY=
BULKSMSBD_SENDER_ID=

# Demo / app-store reviewer account.
DEMO_MOBILE=+8801700000000
DEMO_OTP_CODE=000000
DEMO_PASSWORD=
```

Credentials come from env via `django-environ`, defaulted to `""` — the app boots on a
fresh clone with no secrets and just prints OTPs to the console.

### DRF throttles (the second layer, for the free endpoints)

```python
REST_FRAMEWORK = {
    # Per-scope throttles guard the anonymous auth endpoints (brute force on
    # /auth/login, abuse of /auth/start). Views opt in via `throttle_scope`.
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "10/min",
        "auth_start": "20/min",
        "set_password": "10/min",
    },
}
```

Two independent layers, by design: **DB counters** for anything that spends money,
**cache throttles** for anything that's merely brute-forceable.

---

## 11. Endpoint table

| Method | Path | Sends SMS? | Purpose |
|--------|------|-----------|---------|
| `POST` | `/api/v1/auth/start/` | sometimes | Lookup mobile → `{"next": "password"\|"otp"}`; auto-sends on the otp branch |
| `POST` | `/api/v1/auth/login/` | no | Mobile + password → tokens + user |
| `POST` | `/api/v1/auth/otp/request/` | **yes** | Send / resend OTP |
| `POST` | `/api/v1/auth/password/reset/` | **yes** | Forgot password (named alias of otp/request) |
| `POST` | `/api/v1/auth/otp/verify/` | no | Verify code → tokens + user + `setup_token` |
| `POST` | `/api/v1/auth/set-password/` | no | `setup_token` + new password → tokens + user |
| `POST` | `/api/v1/auth/refresh/` | no | Rotate access token |
| `POST` | `/api/v1/users/me/password/` | no | Change password (current + new), authenticated |

Auth response shape (RFC 6749 style) — `otp/verify` adds `setup_token`, `refresh` omits `user`:

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "Bearer",
  "expires_in": 900,
  "user": { "...": "profile", "password_set": true }
}
```

---

## 12. Testing without sending a single SMS

The console backend means no HTTP mocking. Patch only the code generator so the test
knows what to submit:

```python
_CODE = "123456"
_PATCH_CODE = "shomadhan.users.services._generate_code"


def setUp(self):
    # DRF throttling uses the default cache; clear it so counts don't leak
    # across tests and trip the login/start rate limits.
    cache.clear()


def _verify_otp(self, mobile):
    """Run start + verify for a passwordless number, returning the setup token."""
    with mock.patch(_PATCH_CODE, return_value=_CODE):
        self.client.post(self.START, {"mobile": mobile})
    resp = self.client.post(self.OTP_VERIFY, {"mobile": mobile, "code": _CODE})
    self.assertEqual(resp.status_code, status.HTTP_200_OK)
    return resp.data["setup_token"]
```

The `cache.clear()` in `setUp` is non-optional — without it, scoped-throttle counters
leak between tests and you get flaky 429s in whichever test happens to run tenth.

Cases the suite covers (port all of them):

1. **New user** — start → `otp`, no `User` row yet, verify → set-password → tokens, password checks out.
2. **Backward compatibility** — verify still returns `access_token` / `refresh_token` / `user`, plus `setup_token`, with `password_set: false`.
3. **Invalid OTP** → 400.
4. **Returning user** — start → `password`, and **assert no `OTPRequest` row was created** (this is the test that guards your SMS bill).
5. **Unknown number login** → 401.
6. **Legacy OTP-only user** — start → `otp` even though a `User` row exists (the `has_password_set` trap).
7. **Forgot password** — reset → verify → set-password; old password now 401s, new one 200s.
8. **Weak password** → 400.
9. **Tampered `setup_token`** → 400.
10. **Login throttle** — 12 bad logins, last one is 429.

---

## 13. Port checklist

1. Copy `OTPRequest` into your users app; `makemigrations users --name add_otp_request`.
2. Copy `_send_sms` and swap the provider branch for yours. Keep the `console` default and the `timeout`.
3. Copy `send_otp` / `verify_otp`. Tune the two rate limits and the code length.
4. Copy `normalise_mobile` and change the country prefix.
5. Copy the three signing helpers + `complete_password_setup`. Change `_SETUP_TOKEN_SALT` to your namespace.
6. Copy `has_password_set` — **especially** if the project has legacy passwordless users.
7. Copy `start_auth` / `authenticate_with_password`.
8. Add the views, the `_auth_response` helper, and the problem+json error constants.
9. Add settings + `.env.example` entries; pin `OTP_BACKEND = "console"` in test settings.
10. Add `throttle_scope` to login / start / set-password and the matching `DEFAULT_THROTTLE_RATES`.
11. Copy the test suite; run it before wiring real credentials.

### Things to keep in mind when adapting

- **Never store the plaintext code.** Hash + salt, always.
- **Never let a service reach for `request`.** Services take primitives (`mobile`, `code`, `ip`); the view extracts `REMOTE_ADDR`. That's what makes them testable and reusable from a management command.
- **Behind a load balancer, `REMOTE_ADDR` is the proxy.** You must trust and parse `X-Forwarded-For` (or set `USE_X_FORWARDED_HOST` / use `django-ipware`) or the per-IP limit collapses into one global bucket.
- **`OTPRequest` grows forever.** Add a periodic cleanup (`created_at < now - 30 days`) once volume matters — but keep the window longer than the rate-limit window.
- **Deleting an account must wipe its OTP rows.** They're keyed by mobile with no FK, so no cascade fires:

  ```python
  @transaction.atomic
  def delete_account(user) -> None:
      """Hard-delete the user and their account-scoped data.

      OTPRequest is keyed by mobile (no FK), so wipe those explicitly to avoid
      orphans skewing rate-limit queries for the next user of that number.
      """
      if user.mobile:
          OTPRequest.objects.filter(mobile=user.mobile).delete()
      user.delete()
  ```

  Bangladeshi numbers get recycled by carriers — a stale row would eat the next owner's
  rate-limit budget.
