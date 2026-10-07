from django.core.exceptions import ValidationError


def clean_student_audience(attrs, instance=None) -> dict:
    """A group only means something within a class level; clearing the class also clears the group.

    On an edit, a field not being sent is checked as it is saved on `instance`.
    """
    if "class_level" in attrs and attrs["class_level"] is None and "group" not in attrs:
        attrs["group"] = None
    class_level = attrs.get("class_level", getattr(instance, "class_level", None))
    group = attrs.get("group", getattr(instance, "group", None))
    if group is not None and class_level is None:
        raise ValidationError({"group_id": "Choose a class before a group."})
    if group is not None and group.is_common:
        raise ValidationError({"group_id": f"Every student takes {group.name}; choose your own group instead."})
    return attrs
