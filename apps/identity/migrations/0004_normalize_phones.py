"""Rewrite every stored phone number into the canonical `01XXXXXXXXX` form.

`apps.identity.phones.normalize_phone` now runs on every way a number can
enter the system, so new rows are canonical. This brings the rows that were
written before that.

**Collisions are reported, not resolved.** If `01810001111` and
`+8801810001111` are already two separate accounts, they are two separate
people as far as this migration knows -- with their own enrolments, orders
and exam attempts -- and merging them is a judgement call about whose history
survives. So the account that got furthest (registered, then oldest) is
normalised and the others are left exactly as they are, with a warning naming
every id involved. Nothing is deleted and the migration does not fail: a
stuck deploy helps nobody, and the duplicates are already in production.

The normalisation function is copied in rather than imported. A migration has
to keep doing what it did on the day it ran, and importing live code means a
later edit silently changes history.
"""

import re

from django.db import migrations

_SEPARATORS = re.compile(r"[^\d+]")


def _normalize(raw):
    if not raw:
        return raw
    digits = _SEPARATORS.sub("", str(raw).strip()).lstrip("+")
    for prefix in ("00880", "880"):
        if digits.startswith(prefix):
            digits = digits[len(prefix) :]
            break
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    return digits


def normalize(apps, schema_editor):
    User = apps.get_model("identity", "User")
    OTP = apps.get_model("identity", "OTP")

    groups = {}
    for user in User.objects.exclude(phone=None).exclude(phone="").order_by("pk"):
        canonical = _normalize(user.phone)
        if canonical:
            groups.setdefault(canonical, []).append(user)

    collisions = []
    for canonical, users in groups.items():
        if len(users) > 1:
            # Most-complete account first: registered beats placeholder, and
            # among equals the oldest is the one with the history.
            users.sort(key=lambda u: (u.registered_at is None, u.pk))
            collisions.append((canonical, users))
        winner = users[0]
        if winner.phone != canonical:
            winner.phone = canonical
            winner.save(update_fields=["phone"])

    for user in User.objects.exclude(guardian_phone=None).exclude(guardian_phone=""):
        canonical = _normalize(user.guardian_phone)
        if canonical and canonical != user.guardian_phone:
            user.guardian_phone = canonical
            user.save(update_fields=["guardian_phone"])

    # Pending codes have to follow the account, or the code a student is
    # holding stops matching the number they will now be asked for.
    for otp in OTP.objects.exclude(phone=None).exclude(phone=""):
        canonical = _normalize(otp.phone)
        if canonical and canonical != otp.phone:
            otp.phone = canonical
            otp.save(update_fields=["phone"])

    if collisions:
        print("")
        print("  !! Duplicate accounts found -- these need a human decision.")
        print("     One account per number was normalised; the rest were left")
        print("     untouched so no history is lost. Merge them by hand.")
        for canonical, users in collisions:
            print(f"     {canonical}:")
            for i, user in enumerate(users):
                state = "kept" if i == 0 else "left as-is"
                print(f"       #{user.pk}  {user.phone!r}  {user.name!r}  [{state}]")
        print("")


class Migration(migrations.Migration):
    dependencies = [("identity", "0003_add_registered_at")]

    # Reverse is a no-op: the original spellings are gone, and there is
    # nothing to put back that would be more correct than what is there.
    operations = [migrations.RunPython(normalize, migrations.RunPython.noop)]
