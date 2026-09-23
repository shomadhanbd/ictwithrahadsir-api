"""Create the four `auth.Group` rows that `Role` names.

`User.set_role` does `Group.objects.get(name=role)` and `apps.identity.signals`
grants each group its permissions, so both assume the rows already exist. They
are reference data, not user data: every environment -- including the test
database, which is built from migrations alone -- needs them before a single
user can be created.
"""

from django.db import migrations

from apps.identity.roles import Role


def create_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for role in Role.values:
        Group.objects.using(schema_editor.connection.alias).get_or_create(name=role)


def drop_role_groups(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.using(schema_editor.connection.alias).filter(name__in=Role.values).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(create_role_groups, drop_role_groups),
    ]
