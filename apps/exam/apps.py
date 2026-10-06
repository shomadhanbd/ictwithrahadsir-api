from django.apps import AppConfig


class ExamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.exam'
    label = 'exam'
    verbose_name = 'Exams'

    def ready(self):
        from apps.exam import providers, signals  # noqa: F401

        providers.register()
