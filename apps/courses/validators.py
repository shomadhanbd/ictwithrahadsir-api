import re

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _

MAX_ITEMS = 20
ICON_PATTERN = re.compile(r"^[a-z0-9-]{1,50}$")


def course_errors(*, class_level, group, batch, starts_on, ends_on) -> dict:
    """Cross-field rules on a course, as {field: message}; empty if valid."""
    errors = {}
    if class_level is None:
        if group is not None:
            errors["group"] = _("A group needs a class level.")
        if batch is not None:
            errors["batch"] = _("A batch needs a class level.")
    elif batch is not None and batch.class_level_id != class_level.pk:
        errors["batch"] = _("This batch belongs to a different class level.")
    if starts_on and ends_on and ends_on < starts_on:
        errors["ends_on"] = _("A course cannot end before it starts.")
    return errors


@deconstructible
class ItemListValidator:
    """A list of objects with exactly the given string keys."""

    def __init__(self, required, optional=()):
        self.required = tuple(required)
        self.optional = tuple(optional)

    def __call__(self, value):
        if not isinstance(value, list):
            raise ValidationError("Must be a list.")
        if len(value) > MAX_ITEMS:
            raise ValidationError(f"At most {MAX_ITEMS} items.")

        allowed = set(self.required) | set(self.optional)
        for index, item in enumerate(value):
            where = f"Item {index + 1}"
            if not isinstance(item, dict):
                raise ValidationError(f"{where}: must be an object.")
            unknown = set(item) - allowed
            if unknown:
                raise ValidationError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}.")
            for key in self.required:
                if not isinstance(item.get(key), str) or not item[key].strip():
                    raise ValidationError(f"{where}: `{key}` is required.")
            for key in self.optional:
                if key in item and not isinstance(item[key], str):
                    raise ValidationError(f"{where}: `{key}` must be text.")
            if "icon" in item and not ICON_PATTERN.match(item["icon"]):
                raise ValidationError(f"{where}: `icon` must be an icon name such as `video`.")

    def __eq__(self, other):
        return (
            isinstance(other, ItemListValidator) and self.required == other.required and self.optional == other.optional
        )


validate_learning_outcomes = ItemListValidator(required=["title", "icon"])
validate_titles = ItemListValidator(required=["title"])
validate_highlights = ItemListValidator(required=["title", "icon"], optional=["description"])
validate_faqs = ItemListValidator(required=["question", "answer"])


def validate_course(**fields):
    """`course_errors` raised with the API's `<relation>_id` field names."""
    errors = course_errors(**fields)
    if errors:
        relations = {"class_level", "group", "batch"}
        raise ValidationError(
            {(f"{field}_id" if field in relations else field): [message] for field, message in errors.items()}
        )


def validate_section_in_course(section, course):
    if section is not None and course is not None and section.course_id != course.pk:
        raise ValidationError({"section_id": "This section belongs to another course."})


def validate_section_stays_in_course(section, course):
    """A section's lessons, exams and students' progress belong to its course, so it never changes course."""
    if section is not None and course is not None and section.course_id != course.pk:
        raise ValidationError({"course_id": "A section cannot be moved to another course; its lessons belong here."})


def validate_content_type_change(content, new_type):
    from apps.courses.models import Content  # models import this module

    if content is None or new_type == content.type:
        return
    if content.type == Content.Type.EXAM:
        raise ValidationError("An exam lesson's type cannot change. Delete it and add a new lesson instead.")
    if new_type == Content.Type.EXAM:
        raise ValidationError("A lesson cannot become an exam. Add a new exam lesson instead.")


def validate_valid_till_in_future(valid_till, now):
    if valid_till is not None and valid_till <= now:
        raise ValidationError({"valid_till": ["Must be in the future."]})
