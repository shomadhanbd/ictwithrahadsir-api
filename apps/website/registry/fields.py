"""The building blocks of the website registry: what a section and its fields are, and short constructors."""

from dataclasses import dataclass, field

# Lucide icon names the website can draw; keep in step with the web and admin `icons.ts`.
ICONS = (
    "globe",
    "network",
    "binary",
    "code-xml",
    "braces",
    "database",
    "monitor-play",
    "radio",
    "list-checks",
    "file-text",
    "calendar-clock",
    "message-circle-question",
    "mouse-pointer-click",
    "credit-card",
    "play-circle",
    "clipboard-check",
    "pen-line",
    "bar-chart-3",
    "messages-square",
    "book-open",
    "graduation-cap",
    "users",
    "target",
    "trophy",
    "lightbulb",
    "smartphone",
    "star",
    "check",
)

STAT_METRICS = (
    ("courses", "Published courses (counted)"),
    ("students", "Enrolled students (counted)"),
    ("teachers", "Teachers (counted)"),
    ("custom", "Custom number"),
)

SOCIAL_PLATFORMS = (
    ("youtube", "YouTube"),
    ("facebook", "Facebook"),
    ("instagram", "Instagram"),
    ("whatsapp", "WhatsApp"),
)

FIELD_TYPES = ("text", "textarea", "html", "image", "link", "email", "icon", "choice", "list")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    type: str
    default: object = ""
    required: bool = False
    help: str = ""
    # (value, label) pairs, for `icon` and `choice`.
    choices: tuple = ()
    # A `list` field's item fields.
    fields: tuple = ()
    max_items: int = 0

    def __post_init__(self):
        if self.type not in FIELD_TYPES:
            raise ValueError(f"Unknown field type {self.type!r} for {self.name!r}.")


@dataclass(frozen=True)
class SectionSpec:
    key: str
    page: str
    title: str
    fields: tuple
    description: str = ""
    # Site-wide settings, page headings and policy pages are always shown.
    can_hide: bool = True
    defaults: dict = field(init=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "defaults", {f.name: f.default for f in self.fields})


def text(name, label, default="", **kw):
    return FieldSpec(name, label, "text", default, **kw)


def textarea(name, label, default="", **kw):
    return FieldSpec(name, label, "textarea", default, **kw)


def html(name, label, default="", **kw):
    return FieldSpec(name, label, "html", default, **kw)


def image(name, label, default="", **kw):
    return FieldSpec(name, label, "image", default, **kw)


def link(name, label, default="", **kw):
    return FieldSpec(name, label, "link", default, **kw)


def email(name, label, default="", **kw):
    return FieldSpec(name, label, "email", default, **kw)


def choice(name, label, choices, default, **kw):
    return FieldSpec(name, label, "choice", default, required=True, choices=tuple(choices), **kw)


def icon(name="icon", label="Icon", default="check"):
    return FieldSpec(name, label, "icon", default, required=True, choices=tuple((i, i) for i in ICONS))


def items(name, label, item_fields, default, max_items=12, **kw):
    return FieldSpec(name, label, "list", default, fields=tuple(item_fields), max_items=max_items, **kw)


def heading(default, label="Heading"):
    return text("heading", label, default, required=True)


def subtitle(default, label="Subtitle"):
    return textarea("subtitle", label, default)
