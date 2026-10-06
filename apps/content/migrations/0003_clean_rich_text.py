from django.db import migrations

from apps.core.html import clean_html


def clean(apps, schema_editor):
    Notice = apps.get_model("content", "Notice")
    for notice in Notice.objects.exclude(body="").only("pk", "body").iterator():
        if clean_html(notice.body) != notice.body:
            notice.body = clean_html(notice.body)
            notice.save(update_fields=["body"])

    Page = apps.get_model("content", "Page")
    for page in Page.objects.filter(value_type="html").exclude(value="").only("pk", "value").iterator():
        if clean_html(page.value) != page.value:
            page.value = clean_html(page.value)
            page.save(update_fields=["value"])


class Migration(migrations.Migration):
    dependencies = [("content", "0002_seed_home_pages")]

    operations = [migrations.RunPython(clean, migrations.RunPython.noop)]
