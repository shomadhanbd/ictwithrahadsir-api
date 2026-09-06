"""One canonical way to write a Bangladeshi mobile number.

`phone` is this project's `USERNAME_FIELD`, it is unique, and OTPs are keyed
on it. So every place a number arrives -- the web sign-up form, the login
form, the admin panel, a bulk-import spreadsheet -- has to agree on how it is
spelled, or the same person becomes two accounts:

    01810001111        what the sign-up form usually sends
    +8801810001111     what a student copies out of their contacts
    8801810001111      what a spreadsheet exported from a phone tends to hold
    1810001111         what happens when a leading zero is lost to a number
                       column in Excel
    018-1000-1111      what someone types when being helpful

All five are one number. Before this existed they were five accounts, and a
student who had registered as one of them could request a code against
another and never receive a login -- the code went to a row that was not
theirs.

The canonical form is the 11-digit local one, `01XXXXXXXXX`, because that is
what the existing data is overwhelmingly written in and what the SMS backend
expects.

Deliberately *not* a validator. Anything that does not look like a
Bangladeshi mobile is returned cleaned but otherwise untouched: rejecting
here would turn an odd-but-real number in the existing roster into an account
nobody can sign in to, which is a worse failure than storing it as typed.
"""

import re

_SEPARATORS = re.compile(r"[^\d+]")


def normalize_phone(raw: str | None) -> str | None:
    """Return `raw` as `01XXXXXXXXX`, or cleaned-but-unchanged if it isn't one.

    Idempotent -- calling it on an already-normalised number is a no-op, which
    is what lets it sit on both the serializer field and `create_user`
    without the two having to know about each other.
    """
    if not raw:
        return raw

    digits = _SEPARATORS.sub("", str(raw).strip()).lstrip("+")

    # +880 / 00880 / 880 country code -> local
    for prefix in ("00880", "880"):
        if digits.startswith(prefix):
            digits = digits[len(prefix) :]
            break

    # a leading zero lost somewhere between a spreadsheet and here
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits

    return digits
