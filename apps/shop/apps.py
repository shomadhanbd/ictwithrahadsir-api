from django.apps import AppConfig


class ShopConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.shop'
    label = 'shop'

    def ready(self):
        # `courses` needs `has_order` but must not import this app -- see
        # apps/courses/selectors.py. Fill the hole it declares.
        from apps.courses import selectors as course_selectors
        from apps.shop.selectors import ordered_course_ids

        course_selectors.ordered_course_ids_provider = ordered_course_ids
