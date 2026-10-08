from django.db import models

from apps.core.text.html import clean_html


class HtmlTextField(models.TextField):
    """Rich text; script is stripped on every save, whatever writes it (the API, Django's admin, a shell)."""

    def pre_save(self, model_instance, add):
        value = clean_html(getattr(model_instance, self.attname))
        setattr(model_instance, self.attname, value)
        return value
