from django.db import migrations

from apps.core.html import clean_html


def clean(apps, schema_editor):
    for model, fields in (("Course", ["description"]), ("Content", ["note_body", "video_description"])):
        Model = apps.get_model("courses", model)
        for row in Model.objects.only("pk", *fields).iterator():
            changed = [f for f in fields if getattr(row, f) and clean_html(getattr(row, f)) != getattr(row, f)]
            for field in changed:
                setattr(row, field, clean_html(getattr(row, field)))
            if changed:
                row.save(update_fields=changed)


class Migration(migrations.Migration):
    dependencies = [("courses", "0008_highlight_icons")]

    operations = [migrations.RunPython(clean, migrations.RunPython.noop)]
