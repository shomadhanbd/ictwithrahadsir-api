from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.identity'
    label = 'identity'

    def ready(self):
        # Imported here, not at module scope: the app registry must be ready.
        from apps.identity import signals  # noqa: F401
