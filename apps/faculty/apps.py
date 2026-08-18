from django.apps import AppConfig


class FacultyConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.faculty'
    label = 'faculty'

    def ready(self):
        # Registers the receivers in apps.faculty.signals. Imported here, not
        # at module scope, because the models they reference are not loaded
        # until the app registry is ready.
        from apps.faculty import signals  # noqa: F401
