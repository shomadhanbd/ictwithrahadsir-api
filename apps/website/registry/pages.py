"""The headings of the other pages, and the panel beside the sign-in forms."""

from apps.website.registry.fields import SectionSpec, heading, icon, items, text, textarea

SECTIONS = (
    SectionSpec(
        "courses.hero",
        "courses",
        "Heading",
        can_hide=False,
        fields=(
            text("title", "Heading", "আপনার জন্য সঠিক কোর্সটি খুঁজে নিন", required=True),
            textarea("subtitle", "Subtitle", "শ্রেণি, গ্রুপ বা ব্যাচ বেছে নিন — লাইভ ক্লাস থেকে রেকর্ডেড কোর্স, সব এক জায়গায়।"),
        ),
    ),
    SectionSpec(
        "materials.hero",
        "materials",
        "Heading",
        can_hide=False,
        fields=(
            text("title", "Heading", "স্টাডি ম্যাটেরিয়াল", required=True),
            textarea(
                "subtitle",
                "Subtitle",
                "বই, সাজেশন, পরীক্ষার প্রস্তুতির ভিডিও আর মোটিভেশন — আইসিটি প্রস্তুতির সব ম্যাটেরিয়াল এক জায়গায়।",
            ),
        ),
    ),
    SectionSpec(
        "notice.hero",
        "notice",
        "Heading",
        can_hide=False,
        fields=(
            text("title", "Heading", "নোটিশ সমূহ", required=True),
            textarea("subtitle", "Subtitle", "সর্বশেষ ঘোষণা ও গুরুত্বপূর্ণ আপডেট এক জায়গায়।"),
        ),
    ),
    SectionSpec(
        "auth.panel",
        "auth",
        "Sign-in panel",
        can_hide=False,
        description="Beside the sign-in and sign-up forms on wide screens.",
        fields=(
            heading("ICT-তে সেরা প্রস্তুতি শুরু হোক এখান থেকেই।"),
            items(
                "points",
                "Points",
                [icon(), text("text", "Point", required=True)],
                [
                    {"icon": "monitor-play", "text": "লাইভ ক্লাস + রেকর্ডেড সাপোর্ট"},
                    {"icon": "book-open", "text": "সাজেশন, শর্টনোট ও লেকচার শিট"},
                    {"icon": "graduation-cap", "text": "অধ্যায় শেষে পরীক্ষা ও র‍্যাঙ্কিং"},
                ],
                max_items=5,
            ),
        ),
    ),
)
