from django.db import migrations


def move_ebooks(apps, schema_editor):
    """Each e-book of the retired `content` app becomes a book item in a free "ই-বুক" topic under a "বই" category.

    A fresh database has no `content_ebook` table and skips this."""
    connection = schema_editor.connection
    if "content_ebook" not in connection.introspection.table_names():
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT title, description, booking_link, preview, image FROM content_ebook ORDER BY id")
        books = cursor.fetchall()
    if not books:
        return
    Category = apps.get_model("materials", "MaterialCategory")
    Topic = apps.get_model("materials", "MaterialTopic")
    Item = apps.get_model("materials", "MaterialItem")
    category, _ = Category.objects.get_or_create(name="বই", defaults={"icon": "book-open"})
    topic = Topic.objects.create(category=category, title="ই-বুক", access="free", is_published=True)
    for order, (title, description, booking_link, preview, image) in enumerate(books):
        Item.objects.create(
            topic=topic,
            kind="book",
            order=order,
            title=title,
            description=description or "",
            # A book without an order link still keeps its sample as the link to open.
            url=booking_link or preview or "",
            image=image or "",
            preview_url=preview or "",
        )


class Migration(migrations.Migration):
    dependencies = [("materials", "0001_initial")]

    operations = [migrations.RunPython(move_ebooks, migrations.RunPython.noop)]
