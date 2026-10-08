"""Brings over the rows of the apps this one replaced: SMS from `notifications`, notices from `content`.

A fresh database has none of the old tables and skips this. On an existing one the rows keep their IDs, so
links to them stay valid; `notifications` is gone from the code, so its table and migration records are
dropped here, while `content` drops its notice tables in its own next migration.
"""

from django.core.management.color import no_style
from django.db import migrations

# (old table, new table), in an order that keeps foreign keys satisfiable.
TABLES = [
    ("notifications_smsmessage", "communication_smsmessage"),
    ("content_noticecategory", "communication_noticecategory"),
    ("content_notice", "communication_notice"),
    ("content_notice_categories", "communication_notice_categories"),
]


def copy(apps, schema_editor):
    connection = schema_editor.connection
    existing = set(connection.introspection.table_names())
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        for old, new in TABLES:
            if old not in existing:
                continue
            old_columns = {c.name for c in connection.introspection.get_table_description(cursor, old)}
            new_columns = [c.name for c in connection.introspection.get_table_description(cursor, new)]
            columns = ", ".join(quote(c) for c in new_columns if c in old_columns)
            cursor.execute(f"INSERT INTO {quote(new)} ({columns}) SELECT {columns} FROM {quote(old)}")

        Notice = apps.get_model("communication", "Notice")
        models = [
            apps.get_model("communication", "SmsMessage"),
            apps.get_model("communication", "NoticeCategory"),
            Notice,
            Notice.categories.through,
        ]
        for statement in connection.ops.sequence_reset_sql(no_style(), models):
            cursor.execute(statement)

        if "notifications_smsmessage" in existing:
            cursor.execute(f"DROP TABLE {quote('notifications_smsmessage')}")
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ["notifications"])


class Migration(migrations.Migration):
    dependencies = [("communication", "0001_initial")]

    operations = [migrations.RunPython(copy, migrations.RunPython.noop)]
