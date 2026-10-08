from django.apps import AppConfig


class WebsiteConfig(AppConfig):
    name = "apps.website"
    label = "website"
    verbose_name = "Website"

    def ready(self):
        from apps.website import signals  # noqa: F401
