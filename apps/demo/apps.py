from django.apps import AppConfig


class DemoConfig(AppConfig):
    """Demo data only. Sits above every domain app, so it may import any of
    them and none may import it."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.demo'
    label = 'demo'
