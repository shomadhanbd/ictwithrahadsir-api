"""Course profile, part one: renames and the `active` -> `status` switch.

Renames keep their data. `active` becomes `status` -- an active course is
published (stamped as published when it was created); an inactive one is
archived if anybody is enrolled on it, so they keep their access, and a draft
otherwise. Each `features` string becomes a `highlights` item, which the
admin then completes with a description and an icon.
"""

from django.db import migrations, models


def forwards(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Enrollment = apps.get_model("courses", "Enrollment")
    enrolled = set(Enrollment.objects.values_list("course_id", flat=True))

    for course in Course.objects.all():
        if course.active:
            course.status = "published"
            course.published_at = course.created_at
        else:
            course.status = "archived" if course.pk in enrolled else "draft"
        # Old features were bare strings. The `highlights` validator wants a
        # description and an icon too, but validators do not run here: the
        # admin fills them in the next time the course is edited.
        course.highlights = [{"title": str(feature)} for feature in (course.features or []) if str(feature).strip()]
        course.save(update_fields=["status", "published_at", "highlights"])


def backwards(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    for course in Course.objects.all():
        course.active = course.status == "published"
        course.features = [item.get("title", "") for item in (course.highlights or [])]
        course.save(update_fields=["active", "features"])


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0004_course_audience"),
    ]

    operations = [
        migrations.RemoveIndex(model_name="course", name="courses_cou_active_bec911_idx"),
        migrations.RenameField(model_name="course", old_name="featured", new_name="is_featured"),
        migrations.RenameField(model_name="course", old_name="fake_user_count", new_name="fake_student_count"),
        migrations.RenameField(model_name="course", old_name="image", new_name="thumbnail"),
        migrations.RenameField(model_name="course", old_name="video", new_name="promo_video"),
        migrations.RenameField(model_name="course", old_name="pdf_link", new_name="syllabus_pdf"),
        migrations.AddField(
            model_name="course",
            name="status",
            field=models.CharField(
                choices=[("draft", "Draft"), ("published", "Published"), ("archived", "Archived")],
                default="draft",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="published_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AddField(
            model_name="course",
            name="highlights",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(model_name="course", name="active"),
        migrations.RemoveField(model_name="course", name="features"),
    ]
