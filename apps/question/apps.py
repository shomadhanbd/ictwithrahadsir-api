from django.apps import AppConfig


class QuestionConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.question'
    label = 'question'

    def ready(self):
        # Registers the receivers in apps.question.signals. Imported here, not
        # at module scope, because the models they reference are not loaded
        # until the app registry is ready.
        from apps.question import signals  # noqa: F401
