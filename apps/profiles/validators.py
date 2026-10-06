from django.core.exceptions import ValidationError


def student_audience_errors(*, class_level, group) -> dict:
    """A group only means something within a class level."""
    if group is not None and class_level is None:
        return {"group_id": "Choose a class before a group."}
    return {}


def clean_student_audience(attrs, instance) -> dict:
    """Clearing the class also clears the group; raises if the pair is inconsistent."""
    if "class_level" in attrs and attrs["class_level"] is None and "group" not in attrs:
        attrs["group"] = None
    errors = student_audience_errors(
        class_level=attrs.get("class_level", getattr(instance, "class_level", None)),
        group=attrs.get("group", getattr(instance, "group", None)),
    )
    if errors:
        raise ValidationError(errors)
    return attrs
