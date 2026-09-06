"""Identity operations: tokens, one-time codes, and bulk user import.

Three small groups, marked by the section headers below. They live in one
module because none of them is big enough to be worth hunting through a
package for; split it the day one of them is.
"""

from django.conf import settings
from django.db import transaction

from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError

from apps.core.services.factory import get_sms_backend
from apps.core.spreadsheets import text
from apps.identity.models import OTP, User
from apps.identity.phones import normalize_phone

# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------


def issue_token(user: User, *, rotate: bool = False) -> str:
    """Return the user's API token, optionally replacing any existing one.

    Rotation matters after a credential change: DRF tokens never expire, so
    without it a token stolen before a password reset stays valid forever
    afterwards -- the reset would not actually lock the attacker out.
    """
    if rotate:
        Token.objects.filter(user=user).delete()
        return Token.objects.create(user=user).key
    token, _ = Token.objects.get_or_create(user=user)
    return token.key


# ---------------------------------------------------------------------------
# One-time codes
# ---------------------------------------------------------------------------


def send_otp(phone: str) -> OTP:
    """Issue a one-time code and text it to `phone`.

    The send lives here rather than on `OTP.issue` so that creating an OTP row
    is not, by itself, a network call: a model save that reaches an SMS
    gateway is impossible to use from a fixture, a migration or a test without
    stubbing the gateway out.
    """
    otp = OTP.issue(phone)
    get_sms_backend().send(phone, settings.SMS_OTP_TEMPLATE.format(code=otp.code))
    return otp


def consume_otp(phone: str, code: str) -> None:
    """Spend `code`, or raise if it is not the live one for `phone`.

    This is a write -- a wrong guess burns an attempt, a right one marks the
    code consumed -- which is why it is here and not in a serializer's
    `validate()`, where it used to sit. Two things came of that:

    * A validator that changes state reads as if it does not.
    * `PasswordResetAPIView` consumed the code before it had checked the
      phone belonged to anybody, so a perfectly good code was spent on an
      error that had nothing to do with it. Callers now look the account up
      first and call this last.
    """
    if not OTP.verify(phone, code):
        raise ValidationError({"otp": ["Invalid or expired OTP."]})


# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------


@transaction.atomic
def import_users(records: list[dict]) -> dict:
    """Create student accounts from parsed spreadsheet rows.

    Returns `{created, skipped}`. A row is skipped when it has no phone, or
    when its phone or email already belongs to somebody -- silently, because
    re-uploading a sheet that partly overlaps the roster is the normal way
    this screen gets used.

    The existing keys are pulled up front rather than queried per row: the
    original ran a uniqueness query for every line in the file and let a
    duplicate email reach the database as an unhandled IntegrityError, i.e. a
    500 halfway through an import.
    """
    taken_phones = set(User.objects.exclude(phone=None).values_list('phone', flat=True))
    taken_emails = set(User.objects.exclude(email=None).values_list('email', flat=True))

    created, skipped = 0, 0
    for record in records:
        # Normalised before the duplicate check, not after: the stored
        # numbers are canonical, so a sheet holding +8801... would otherwise
        # match nothing and re-create the whole roster.
        phone = normalize_phone(text(record, 'phone'))
        email = text(record, 'email') or None

        if not phone or phone in taken_phones or (email and email in taken_emails):
            skipped += 1
            continue

        User.objects.create_user(
            phone=phone,
            name=text(record, 'name'),
            email=email,
            institution=text(record, 'institution') or None,
            role=User.Role.STUDENT,
        )
        taken_phones.add(phone)
        if email:
            taken_emails.add(email)
        created += 1

    return {'created': created, 'skipped': skipped}
