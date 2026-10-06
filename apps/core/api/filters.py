from django_filters import rest_framework as filters


def id_filterset(model, *fields):
    """A FilterSet taking each of `fields` (e.g. `course_id`) as an exact id."""
    attrs = {field: filters.NumberFilter(field_name=field) for field in fields}
    attrs["Meta"] = type("Meta", (), {"model": model, "fields": list(fields)})
    return type(f"{model.__name__}Filter", (filters.FilterSet,), attrs)
