from django.apps import AppConfig


class CoursesConfig(AppConfig):
    name = 'apps.courses'
    label = 'courses'

    def ready(self):
        from apps.core import providers
        from apps.courses import signals  # noqa: F401
        from apps.courses.services import hand_over_teaching

        providers.register("profiles.hand_over_teaching", hand_over_teaching)
