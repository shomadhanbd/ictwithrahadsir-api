from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from rest_framework.authtoken.models import Token
from rest_framework.exceptions import Throttled, ValidationError

from apps.core.sms import get_sms_backend
from apps.identity.models import OTP, User
from apps.profiles.models import GuardianProfile, StudentProfile

# -- tokens ------------------------------------------------------------------


def revoke_tokens(user: User) -> None:
    Token.objects.filter(user=user).delete()


def issue_token(user: User, *, rotate: bool = False) -> str:
    if rotate:
        with transaction.atomic():
            revoke_tokens(user)
            return Token.objects.create(user=user).key
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


# -- accounts ----------------------------------------------------------------


def authenticate_user(*, password: str, phone: str) -> User:
    """Phone plus password. Email is not an alternative identifier."""
    user = User.objects.filter(phone=phone).first()

    if user is None or not user.check_password(password):
        raise ValidationError({"password": ["Invalid credentials."]})
    if not user.is_active:
        raise ValidationError({"password": ["This account has been deactivated."]})
    return user


def deactivate_user(user: User) -> None:
    user.is_active = False
    user.save(update_fields=["is_active"])
    revoke_tokens(user)


# -- one-time codes ----------------------------------------------------------


def is_demo_phone(phone: str) -> bool:
    """The reviewer number, which skips the send and takes a fixed code."""
    return bool(settings.DEMO_PHONE) and phone == settings.DEMO_PHONE


def send_otp(phone: str, purpose: str, meta: dict | None = None) -> OTP | None:
    if is_demo_phone(phone):
        return None
    otp = OTP.issue(phone, purpose, meta=meta)
    get_sms_backend().send(phone, settings.SMS_OTP_TEMPLATE.format(code=otp.code))
    return otp


def consume_otp(phone: str, code: str, purpose: str) -> None:
    if is_demo_phone(phone) and str(code or "") == settings.DEMO_OTP_CODE:
        return
    if not OTP.verify(phone, code, purpose):
        raise ValidationError({"otp": ["Invalid or expired OTP."]})


def request_login_otp(phone: str, meta: dict | None = None) -> dict:
    user = User.objects.filter(phone=phone).first()
    wait = OTP.seconds_until_resend(phone)
    if not wait:
        send_otp(phone, OTP.Purpose.VERIFY, meta=meta)
    return {
        "user_exist": bool(user),
        "password_exist": bool(user and user.has_usable_password()),
        "resend_in": wait,
    }


# -- sign-up -----------------------------------------------------------------


def verify_phone(phone: str, code: str) -> tuple[User, bool]:
    """Consume a code; return the account and whether it is still to register."""
    consume_otp(phone, code, OTP.Purpose.VERIFY)

    user = User.objects.filter(phone=phone).first()
    if user is None:
        try:
            with transaction.atomic():
                user = User.objects.create_unverified(phone)
        except IntegrityError:
            user = User.objects.get(phone=phone)

    user.phone_verified_at = timezone.now()
    user.save(update_fields=["phone_verified_at"])

    # No password means sign-up never finished, not that the phone is unverified.
    return user, not user.has_usable_password()


def register_user(
    *,
    user: User,
    name: str,
    password: str,
    institution: str | None = None,
    educational_session: str | None = None,
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

        profile, _ = StudentProfile.objects.get_or_create(user=user)
        if institution is not None:
            profile.institution = institution
        if educational_session is not None:
            profile.educational_session = educational_session
        profile.save()
        # Blank, but present: `StudentProfileSerializer` reads the guardian's
        # name and number through this relation, and an admin editing the
        # student later expects a row to fill in rather than to create.
        GuardianProfile.objects.get_or_create(student=profile)
    return user


# -- password reset ----------------------------------------------------------


def start_password_reset(phone: str, meta: dict | None = None) -> None:
    if not User.objects.filter(phone=phone).exists():
        raise ValidationError({"phone": ["No account found with this phone number."]})

    wait = OTP.seconds_until_resend(phone)
    if wait:
        raise Throttled(wait=wait)
    send_otp(phone, OTP.Purpose.PASSWORD_RESET, meta=meta)


def reset_password(*, phone: str, code: str, password: str) -> User:
    user = User.objects.filter(phone=phone).first()
    if not user:
        raise ValidationError({"phone": ["No account found with this phone number."]})
    consume_otp(phone, code, OTP.Purpose.PASSWORD_RESET)

    user.set_password(password)
    user.save(update_fields=["password"])
    return user
