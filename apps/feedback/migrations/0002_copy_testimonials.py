"""Staff-typed testimonials of the retired `content` app become approved, featured general feedback.

A fresh database has no `content_testimonial` table and skips this."""

from django.db import migrations


def copy(apps, schema_editor):
    connection = schema_editor.connection
    if "content_testimonial" not in connection.introspection.table_names():
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT name, designation, description, ratings, image, created_at FROM content_testimonial")
        rows = cursor.fetchall()
    Feedback = apps.get_model("feedback", "Feedback")
    for name, designation, description, ratings, image, created_at in rows:
        new = Feedback.objects.create(
            source="general",
            name=name,
            designation=designation or "",
            image=image or "",
            rating=min(max(ratings or 5, 1), 5),
            comment=description or "",
            status="approved",
            is_featured=True,
        )
        Feedback.objects.filter(pk=new.pk).update(created_at=created_at)


class Migration(migrations.Migration):
    dependencies = [("feedback", "0001_initial")]

    operations = [migrations.RunPython(copy, migrations.RunPython.noop)]
