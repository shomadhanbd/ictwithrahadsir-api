from django_filters import rest_framework as filters

from apps.communication.models import Notice


class NoticeFilter(filters.FilterSet):
    category_id = filters.NumberFilter(field_name="categories")

    class Meta:
        model = Notice
        fields = ["category_id"]


class AdminNoticeFilter(filters.FilterSet):
    category = filters.NumberFilter(field_name="categories")

    class Meta:
        model = Notice
        fields = ["category"]
