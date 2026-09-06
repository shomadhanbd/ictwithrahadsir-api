"""Add `registered_at`, and treat everybody who already exists as registered.

The field separates a real account from the placeholder row
`/auth/otp/verify/` creates before `/auth/register/` has run. Existing rows
predate the distinction, so there is no way to tell which of them were
abandoned registrations -- and guessing wrong in the other direction would
drop a real student out of the roster and out of the dashboard count. So
every existing row is backfilled as registered; only rows created from here
on can be placeholders.
"""

from django.db import migrations, models
from django.db.models import F


def backfill(apps, schema_editor):
    User = apps.get_model("identity", "User")
    User.objects.update(registered_at=F("date_joined"))


class Migration(migrations.Migration):
    dependencies = [("identity", "0002_alter_otp_phone")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="registered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        # reverse is a no-op: dropping the column throws the data away anyway
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
