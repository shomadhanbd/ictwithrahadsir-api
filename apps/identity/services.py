import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, get_random_string

from rest_framework.authtoken.models import Token

from apps.communication.models import SmsMessage
from apps.communication.services import send_sms
from apps.core.api.auth.authentication import token_expired
from apps.identity.models import OTP, User
from apps.identity.selectors import account_state, seconds_until_resend
from apps.profiles.services import ensure_student_profile, save_student_profile

BAD_CODE = {"otp": ["Invalid or expired OTP."]}

OTP_SMS_PURPOSE = {
    OTP.Purpose.VERIFY: SmsMessage.Purpose.PHONE_VERIFY,
    OTP.Purpose.PASSWORD_RESET: SmsMessage.Purpose.PASSWORD_RESET,
}


# Tokens


def revoke_tokens(user: User) -> None:
    Token.objects.filter(user=user).delete()


def issue_token(user: User, *, rotate: bool = False) -> str:
    """The user's token with its lifetime restarted; a new one when asked to rotate or when it has expired.

    The expiry slides: every sign-in restarts TOKEN_TTL_DAYS on the one token all devices share, so signing in
    on a phone does not sign the laptop out. A password change or reset rotates it, ending every session.
    """
    with transaction.atomic():
        # One token per user: concurrent sign-ins and rotations for the same user take turns.
        User.objects.select_for_update().filter(pk=user.pk).first()
        current = Token.objects.filter(user=user).first()
        if current is not None and not rotate and not token_expired(current):
            Token.objects.filter(pk=current.pk).update(created=timezone.now())
            return current.key
        revoke_tokens(user)
        return Token.objects.create(user=user).key


# One-time codes


def issue_otp(phone: str, purpose: str, meta: dict | None = None) -> OTP:
    return OTP.objects.create(
        phone=phone,
        purpose=purpose,
        code=get_random_string(settings.OTP_LENGTH, allowed_chars=string.digits),
        meta=meta or {},
    )


def verify_otp(phone: str, code: str, purpose: str) -> bool:
    """Spends the matching usable code; every guess counts as an attempt."""
    otp = OTP.objects.latest_for(phone, purpose)
    if otp is None or not otp.is_usable:
        return False

    # Claim the attempt in the database first, so concurrent guesses cannot all pass the cap.
    claimed = OTP.objects.filter(pk=otp.pk, consumed_at__isnull=True, attempts__lt=settings.OTP_MAX_ATTEMPTS).update(
        attempts=models.F("attempts") + 1
    )
    if not claimed:
        return False
    if not constant_time_compare(otp.code, str(code or "")):
        return False

    # Conditional, so two concurrent verifies cannot both succeed.
    spent = OTP.objects.filter(pk=otp.pk, consumed_at__isnull=True).update(consumed_at=timezone.now())
    return bool(spent)


def _send_otp(phone: str, purpose: str, meta: dict | None = None) -> None:
    if _is_demo_phone(phone):
        return
    otp = issue_otp(phone, purpose, meta=meta)
    send_sms(phone, settings.SMS_OTP_TEMPLATE.format(code=otp.code), purpose=OTP_SMS_PURPOSE[purpose])


def _consume_otp(phone: str, code: str, purpose: str) -> None:
    if _is_demo_code(phone, code, purpose):
        return
    if not verify_otp(phone, code, purpose):
        raise ValidationError(BAD_CODE)


def _is_demo_phone(phone: str) -> bool:
    """The app-store reviewer's number, which gets no SMS and takes a fixed code."""
    return bool(settings.DEMO_PHONE) and phone == settings.DEMO_PHONE


def _is_demo_code(phone: str, code: str, purpose: str) -> bool:
    """The reviewer's fixed code signs in; it never resets a password, or anyone could lock the reviewer out."""
    if purpose != OTP.Purpose.VERIFY or not _is_demo_phone(phone):
        return False
    return str(code or "") == settings.DEMO_OTP_CODE


# Sign up and sign in


def request_login_otp(phone: str, meta: dict | None = None) -> dict:
    wait = seconds_until_resend(phone)
    if not wait:
        _send_otp(phone, OTP.Purpose.VERIFY, meta=meta)
    return {**account_state(phone), "resend_in": wait}


def verify_phone(phone: str, code: str) -> tuple[User, bool]:
    """Consume a code; return the account and whether it is still to register."""
    _consume_otp(phone, code, OTP.Purpose.VERIFY)

    user = User.objects.filter(phone=phone).first()
    if user is None:
        try:
            with transaction.atomic():
                user = User.objects.create_unverified(phone)
        except IntegrityError:
            user = User.objects.get(phone=phone)

    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])
    is_new = not user.has_usable_password()
    return user, is_new


def register_user(
    *,
    user: User,
    name: str,
    password: str,
    institution: str | None = None,
    educational_session: str | None = None,
    class_level=None,
    group=None,
) -> User:
    """Fill in the profile of a phone that has just passed OTP verification."""
    with transaction.atomic():
        user = User.objects.select_for_update().filter(pk=user.pk).first()
        if not user or not user.phone_verified_at:
            raise ValidationError({"phone": ["Phone has not been verified via OTP."]})
        if user.has_usable_password():
            raise ValidationError({"phone": ["This phone number is already registered."]})
        window = timezone.timedelta(seconds=settings.REGISTRATION_WINDOW_SECONDS)
        if timezone.now() - user.phone_verified_at > window:
            raise ValidationError({"phone": ["Phone verification has expired. Please verify your number again."]})

        user.name = name
        user.set_password(password)
        user.save(update_fields=["name", "password"])
        ensure_student_profile(
            user,
            institution=institution,
            educational_session=educational_session,
            class_level=class_level,
            group=group,
        )
    return user


def authenticate_user(*, phone: str, password: str) -> User:
    user = User.objects.filter(phone=phone).first()
    if user is None or not user.check_password(password):
        raise ValidationError({"password": ["Invalid credentials."]})
    if not user.is_active:
        raise ValidationError({"password": ["This account has been deactivated."]})
    return user


# Password reset


def start_password_reset(phone: str, meta: dict | None = None) -> int:
    """Sends a reset code to a known number; returns 0, or the seconds to wait when one was sent too recently."""
    wait = seconds_until_resend(phone)
    if not wait and User.objects.filter(phone=phone).exists():
        _send_otp(phone, OTP.Purpose.PASSWORD_RESET, meta=meta)
    return wait


def reset_password(*, phone: str, code: str, password: str) -> User:
    user = User.objects.filter(phone=phone).first()
    if not user:
        raise ValidationError(BAD_CODE)  # the same answer as a wrong code
    _consume_otp(phone, code, OTP.Purpose.PASSWORD_RESET)
    user.set_password(password)
    user.save(update_fields=["password"])
    return user


# Accounts: the admin user API and the user's own profile


@transaction.atomic
def create_account(data) -> User:
    data = dict(data)
    student = data.pop("student", None)
    password = data.pop("password")
    role = data.pop("role", None)

    user = User.objects.create_user(password=password, role=role, **data)
    save_student_profile(user, student)
    return user


@transaction.atomic
def update_account(user: User, data) -> User:
    data = dict(data)
    student = data.pop("student", None)
    role = data.pop("role", None)
    password_changed = bool(data.get("password"))

    _apply_account_fields(user, data)
    if password_changed:
        revoke_tokens(user)
    if role:
        user.set_role(role)
    save_student_profile(user, student)
    return user


@transaction.atomic
def update_profile(user: User, data) -> User:
    data = dict(data)
    data.pop("current_password", None)
    student = data.pop("student", None)

    _apply_account_fields(user, data)
    save_student_profile(user, student)
    return user


def deactivate_user(user: User) -> None:
    user.is_active = False
    user.save(update_fields=["is_active"])
    revoke_tokens(user)


def _apply_account_fields(user: User, data: dict) -> None:
    password = data.pop("password", None)
    if password:
        user.set_password(password)
    for field, value in data.items():
        setattr(user, field, value)
    user.save()
