from django.db import migrations

# Taka; changed in the admin.
RATES = {"sylhet": 60, "outside": 120}


def seed(apps, schema_editor):
    DeliveryRate = apps.get_model("materials", "DeliveryRate")
    for zone, charge in RATES.items():
        DeliveryRate.objects.get_or_create(zone=zone, defaults={"charge": charge})


class Migration(migrations.Migration):
    dependencies = [("materials", "0003_book_orders")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
