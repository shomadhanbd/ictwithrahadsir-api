"""Brings over what the retired `content` app held, then drops its tables.

Policy pages become `legal.*` sections, the home photo goes into `home.trust`, advertisements become banners.
The counters are not copied: the home numbers are counted now. A fresh database has none of the old tables."""

from django.db import migrations

from apps.website.registry import REGISTRY

LEGAL_KEYS = ("privacy-policy", "terms-and-conditions", "refund-policy")


def copy(apps, schema_editor):
    connection = schema_editor.connection
    tables = set(connection.introspection.table_names())
    Section = apps.get_model("website", "Section")
    Banner = apps.get_model("website", "Banner")

    with connection.cursor() as cursor:
        if "content_page" in tables:
            cursor.execute("SELECT key, value, image FROM content_page")
            for key, value, image in cursor.fetchall():
                if key in LEGAL_KEYS and value:
                    content = {**REGISTRY[f"legal.{key}"].defaults, "body": value}
                    Section.objects.update_or_create(key=f"legal.{key}", defaults={"content": content})
                elif key == "homeBannerImage" and image:
                    content = {**REGISTRY["home.trust"].defaults, "image": image}
                    Section.objects.update_or_create(key="home.trust", defaults={"content": content})

        if "content_advertisement" in tables:
            cursor.execute("SELECT title, link, image FROM content_advertisement ORDER BY id")
            for order, (title, link, image) in enumerate(row for row in cursor.fetchall() if row[2]):
                Banner.objects.create(title=title or "Banner", link=link or "", image=image, order=order)

        cascade = " CASCADE" if connection.vendor == "postgresql" else ""
        for table in sorted(t for t in tables if t.startswith("content_")):
            cursor.execute(f"DROP TABLE IF EXISTS {connection.ops.quote_name(table)}{cascade}")
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["content"])

    apps.get_model("contenttypes", "ContentType").objects.filter(app_label="content").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("website", "0001_initial"),
        ("contenttypes", "0002_remove_content_type_name"),
        # They copy their own rows out of `content` tables first.
        ("communication", "0002_copy_old_data"),
        ("feedback", "0002_copy_testimonials"),
        ("materials", "0002_move_ebooks"),
    ]

    operations = [migrations.RunPython(copy, migrations.RunPython.noop)]
