from django.apps import AppConfig


class IdentityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.identity'
    label = 'identity'

    def ready(self):
        from apps.identity import signals  # noqa: F401
