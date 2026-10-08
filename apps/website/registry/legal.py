"""The policy pages linked from the footer; served one at a time, never in the shared website payload."""

from apps.website.registry.fields import SectionSpec, html, text, textarea

PREFIX = "legal."

#: (slug, title, introduction)
PAGES = (
    ("privacy-policy", "প্রাইভেসি পলিসি", "আপনার দেওয়া তথ্য আমরা কীভাবে সংগ্রহ ও ব্যবহার করি।"),
    ("terms-and-conditions", "টার্মস এন্ড কন্ডিশন", "আমাদের কোর্স ব্যবহারের শর্তাবলি।"),
    ("refund-policy", "রিফান্ড পলিসি", "কোন কোন ক্ষেত্রে ফি ফেরত পাওয়া যায়।"),
)

SECTIONS = tuple(
    SectionSpec(
        f"{PREFIX}{slug}",
        "legal",
        title,
        can_hide=False,
        fields=(
            text("title", "Title", title, required=True),
            textarea("intro", "Introduction", intro),
            html("body", "Text"),
        ),
    )
    for slug, title, intro in PAGES
)
