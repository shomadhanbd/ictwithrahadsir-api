from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.courses'
    label = 'courses'

    def ready(self):
        # Registers the receivers in apps.courses.signals. Imported here, not
        # at module scope, because the models they reference are not loaded
        # until the app registry is ready.
        from apps.courses import signals  # noqa: F401
