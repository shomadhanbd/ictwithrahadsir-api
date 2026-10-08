from django.db import migrations


def move_ebooks(apps, schema_editor):
    """Each e-book becomes a book item in a free "ই-বুক" topic under a "বই" category."""
    EBook = apps.get_model("content", "EBook")
    if not EBook.objects.exists():
        return
    Category = apps.get_model("materials", "MaterialCategory")
    Topic = apps.get_model("materials", "MaterialTopic")
    Item = apps.get_model("materials", "MaterialItem")
    category, _ = Category.objects.get_or_create(name="বই", defaults={"icon": "book-open"})
    topic = Topic.objects.create(category=category, title="ই-বুক", access="free", is_published=True)
    for order, book in enumerate(EBook.objects.order_by("id")):
        Item.objects.create(
            topic=topic,
            kind="book",
            order=order,
            title=book.title,
            description=book.description,
            # A book without an order link still keeps its sample as the link to open.
            url=book.booking_link or book.preview or "",
            image=book.image or "",
            preview_url=book.preview or "",
        )


class Migration(migrations.Migration):
    dependencies = [
        ("materials", "0001_initial"),
        ("content", "0002_seed_home_pages"),
    ]

    operations = [migrations.RunPython(move_ebooks, migrations.RunPython.noop)]
