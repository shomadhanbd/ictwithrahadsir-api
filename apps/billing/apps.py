from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    label = 'billing'
    verbose_name = 'Billing'

    def ready(self):
        from apps.billing import signals  # noqa: F401
        from apps.billing.selectors import course_packages, ordered_course_ids, sold_course_ids
        from apps.core import providers

        providers.register("courses.ordered_course_ids", ordered_course_ids)
        providers.register("courses.course_packages", course_packages)
        providers.register("courses.sold_course_ids", sold_course_ids)
