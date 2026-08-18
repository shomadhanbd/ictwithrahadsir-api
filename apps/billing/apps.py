from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.billing'
    label = 'billing'

    def ready(self):
        # `courses` needs `has_order` but must not import this app -- see
        # apps/courses/selectors.py. Fill the hole it declares.
        from apps.billing.selectors import ordered_course_ids
        from apps.courses import selectors as course_selectors

        course_selectors.ordered_course_ids_provider = ordered_course_ids
