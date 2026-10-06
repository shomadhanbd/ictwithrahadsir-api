from django.apps import AppConfig


class QuestionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.question'
    label = 'question'

    def ready(self):
        from apps.question import signals  # noqa: F401
