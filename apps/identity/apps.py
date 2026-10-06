from django.apps import AppConfig


class IdentityConfig(AppConfig):
    name = 'apps.identity'
    label = 'identity'

    def ready(self):
        from apps.identity import signals  # noqa: F401
