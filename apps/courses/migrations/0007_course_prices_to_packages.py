"""Course prices move to billing: each `CoursePrice` becomes a package.

A course used to carry its own price plans while checkout sold billing
`Product`s, so the price a student saw was not the one they could pay. Each
old plan becomes a single-course product, kept on sale, so nothing that was
for sale stops being for sale:

- `price` is what a student paid that day: the amount less a discount that
  is still running. `base_price` is the full amount, so a discount still
  shows as a struck-through "was" price.
- A plan for a number of days keeps `access_days`; one until a date keeps
  `access_ends_on` (the date part); a relative plan with no length stays
  lifetime.
- Each is named "<course> — <access>" ("— ১ বছর", "— ১ মাস"), the form the
  admin panel gives new prices, rather than after the old plan title.
- `discount_till` has no counterpart on a product. When it passes, an admin
  edits the package's price by hand.

The reverse step does not recreate prices: it is a one-way move, and the
packages it made stay behind (they may have been bought since).
"""

from django.db import migrations
from django.utils import timezone


BANGLA_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def access_label(days, ends_on):
    """The access length in Bangla, as the admin panel names new prices:
    "১ বছর", "১ মাস", "৯০ দিন", "আজীবন" or "<date> পর্যন্ত"."""
    if ends_on:
        return f"{ends_on:%d/%m/%Y} পর্যন্ত".translate(BANGLA_DIGITS)
    if not days:
        return "আজীবন"
    if days % 365 == 0:
        return f"{days // 365} বছর".translate(BANGLA_DIGITS)
    if days % 30 == 0:
        return f"{days // 30} মাস".translate(BANGLA_DIGITS)
    return f"{days} দিন".translate(BANGLA_DIGITS)


def prices_to_packages(apps, schema_editor):
    CoursePrice = apps.get_model("courses", "CoursePrice")
    Course = apps.get_model("courses", "Course")
    Product = apps.get_model("billing", "Product")

    courses = {course.pk: course for course in Course.objects.all()}
    now = timezone.now()

    for plan in CoursePrice.objects.filter(priceable_type="course").order_by("id"):
        course = courses.get(plan.priceable_id)
        if course is None:
            continue

        amount = int(round(plan.amount or 0))
        discount = int(round(plan.discount or 0))
        discount_running = discount > 0 and (plan.discount_till is None or plan.discount_till >= now)
        price = max(amount - discount, 0) if discount_running else amount

        access_days = access_ends_on = None
        if plan.validity_type == "absolute":
            access_ends_on = plan.validity_time.date() if plan.validity_time else None
        else:
            access_days = plan.validity_duration or None

        product = Product.objects.create(
            # Named by what it gives, not the old plan title: several of those
            # said "lifetime" over a 365-day validity.
            title=f"{course.title} — {access_label(access_days, access_ends_on)}"[:255],
            # Historical models skip `save()`, so the slug is built here; the
            # plan's id keeps it unique.
            product_id=f"{course.slug[:260]}-plan-{plan.pk}",
            description="",
            price=price,
            base_price=max(amount, price),
            access_days=access_days,
            access_ends_on=access_ends_on,
            is_active=True,
        )
        product.courses.add(course)


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0006_course_profile_fields"),
        ("billing", "0002_initial"),
    ]

    operations = [
        migrations.RunPython(prices_to_packages, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="courseprice",
            name="courses_cou_priceab_d7de5a_idx",
        ),
        migrations.DeleteModel(
            name="CoursePrice",
        ),
    ]
