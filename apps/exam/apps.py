from django.apps import AppConfig


class ExamConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.exam'
    label = 'exam'
    #: Distinguishes this from `assessment`, which registers its own `Exam`.
    verbose_name = 'Exam Authoring'

    def ready(self):
        # Registers the receivers in apps.exam.signals. Imported here, not at
        # module scope, because the models they reference are not loaded until
        # the app registry is ready.
        from apps.exam import signals  # noqa: F401
