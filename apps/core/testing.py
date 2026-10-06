"""Small helpers shared by the test suites."""

from itertools import count

from rest_framework.authtoken.models import Token

from apps.identity.models import User

_phones = count(1)
_slugs = count(1)


def make_user(*, role=User.Role.STUDENT, phone=None, name=None, **fields):
    """A user with a unique phone number unless one is given."""
    phone = phone or f"0199{next(_phones):07d}"
    return User.objects.create_user(phone=phone, name=name or role.label, role=role, **fields)


def bearer(user) -> dict:
    """Request kwargs that authenticate as `user`."""
    token, _ = Token.objects.get_or_create(user=user)
    return {"HTTP_AUTHORIZATION": f"Bearer {token.key}"}


def next_slug(prefix: str = "item") -> str:
    """A slug no other row in the test run holds; slugs are typed by staff, so tests must supply one."""
    return f"{prefix}-{next(_slugs)}"
