from django_filters import rest_framework as filters

from apps.academic.models import Batch


class PublicBatchFilter(filters.FilterSet):
    class_level = filters.CharFilter(field_name="class_level__slug")

    class Meta:
        model = Batch
        fields = ["class_level"]
