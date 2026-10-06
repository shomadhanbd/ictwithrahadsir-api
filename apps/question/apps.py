from django.apps import AppConfig


class QuestionConfig(AppConfig):
    name = 'apps.question'
    label = 'question'

    def ready(self):
        from apps.question import signals  # noqa: F401
