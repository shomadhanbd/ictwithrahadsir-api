"""Rich text from the admin editors, reduced to markup that cannot run script."""

import nh3

_ATTRIBUTES = {tag: set(names) for tag, names in nh3.ALLOWED_ATTRIBUTES.items()}
_ATTRIBUTES["*"] = _ATTRIBUTES.get("*", set()) | {"class"}


def clean_html(value: str) -> str:
    return nh3.clean(value, attributes=_ATTRIBUTES) if value else value
