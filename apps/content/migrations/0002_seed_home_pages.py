from django.db import migrations

HOME_PAGES = [
    {"key": "homeBannerImage", "value_type": "image", "value": ""},
    {"key": "homeCourseCounter", "value_type": "counter", "value": "0"},
    {"key": "homeStudentCounter", "value_type": "counter", "value": "0"},
    {"key": "homeInstructorCounter", "value_type": "counter", "value": "0"},
]


def seed_home_pages(apps, schema_editor):
    Page = apps.get_model("content", "Page")
    for entry in HOME_PAGES:
        Page.objects.get_or_create(
            key=entry["key"],
            defaults={
                "slug": entry["key"],
                "value_type": entry["value_type"],
                "value": entry["value"],
            },
        )


def remove_home_pages(apps, schema_editor):
    Page = apps.get_model("content", "Page")
    Page.objects.filter(key__in=[entry["key"] for entry in HOME_PAGES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_home_pages, remove_home_pages),
    ]
