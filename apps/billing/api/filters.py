from django.db.models import Count

from django_filters import rest_framework as filters

from apps.billing.models import Product


class AdminProductFilter(filters.FilterSet):
    course_id = filters.NumberFilter(field_name='courses__id')
    is_active = filters.BooleanFilter()
    kind = filters.ChoiceFilter(choices=[('bundle', 'Bundle'), ('single', 'Single course')], method='filter_kind')

    class Meta:
        model = Product
        fields = ['course_id', 'is_active', 'kind']

    def filter_kind(self, queryset, name, value):
        links = Product.courses.through.objects.values('product_id').annotate(n=Count('course_id'))
        ids = links.filter(n__gt=1) if value == 'bundle' else links.filter(n=1)
        return queryset.filter(pk__in=ids.values('product_id'))
