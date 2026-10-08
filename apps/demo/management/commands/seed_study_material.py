from django.core.management.base import BaseCommand

from apps.academic.models import ClassLevel
from apps.courses.models import Course
from apps.materials.models import BookOrder, MaterialCategory, MaterialItem, MaterialTopic

VIDEOS = ["https://www.youtube.com/watch?v=K3R-NRESyzU", "https://www.youtube.com/watch?v=g7dAav4kCdk"]
PDF = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
STUDENTS_ONLY = "demo-hsc-physics-live-2027"

CATEGORIES = [
    ("বই", "book-open"),
    ("সাজেশন", "file-text"),
    ("পরীক্ষার প্রস্তুতি", "target"),
    ("মোটিভেশন", "rocket"),
    ("নোট ও শিট", "pen-tool"),
    ("দরকারি লিংক", "lightbulb"),
]

CHAPTERS = [
    "তথ্য ও যোগাযোগ প্রযুক্তি: বিশ্ব ও বাংলাদেশ প্রেক্ষিত",
    "কমিউনিকেশন সিস্টেম ও নেটওয়ার্কিং",
    "সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস",
    "ওয়েব ডিজাইন পরিচিতি এবং HTML",
    "প্রোগ্রামিং ভাষা",
    "ডেটাবেজ ম্যানেজমেন্ট সিস্টেম",
]

MOTIVATION = [
    "আইসিটিতে A+ পাওয়া কি কঠিন?",
    "পড়ায় মন বসে না? এই ৫টি কাজ করুন",
    "ফেল করার ভয় কাটাবেন যেভাবে",
    "মোবাইল আসক্তি থেকে মুক্তির উপায়",
    "টপারদের পড়ার রুটিন",
    "প্রতিদিন ২ ঘণ্টা পড়ে A+ সম্ভব?",
    "পরীক্ষার আগের রাতে যা করবেন না",
    "হতাশ লাগলে এই ভিডিওটি দেখুন",
    "সিলেবাস শেষ না হলে কী করবেন",
    "নিজের ওপর বিশ্বাস রাখুন",
    "গ্রুপ স্টাডি নাকি একা পড়া?",
    "রেজাল্ট খারাপ হলেও জীবন থেমে থাকে না",
    "লক্ষ্য ঠিক করবেন যেভাবে",
    "সকালে পড়া নাকি রাতে?",
]


def videos(titles):
    return [("video", title, VIDEOS[i % 2]) for i, title in enumerate(titles)]


#: (category, title, description, class slug or None, students-only course slug or None, items)
#: An item is (kind, title, url) or (kind, title, url, {extra fields}).
TOPICS = [
    (
        "বই",
        "রাহাদ স্যারের বই",
        "ঘরে বসে অর্ডার করুন।",
        None,
        None,
        [
            (
                "book",
                "আইসিটি সম্পূর্ণ গাইড",
                "",
                {"price": 350, "description": "ছয়টি অধ্যায়ের পূর্ণ আলোচনা, সৃজনশীল ও বহুনির্বাচনী প্রশ্নসহ।"},
            ),
            (
                "book",
                "আইসিটি এমসিকিউ মাস্টার",
                "",
                {"price": 220, "description": "অধ্যায়ভিত্তিক ১০০০+ এমসিকিউ, প্রতিটির ব্যাখ্যাসহ।"},
            ),
        ],
    ),
    (
        "পরীক্ষার প্রস্তুতি",
        "পরীক্ষার আগে কী করবেন",
        "শেষ সময়ের রিভিশন, সময় ভাগ আর পরীক্ষার হলের কৌশল।",
        None,
        None,
        [
            *videos(["শেষ ৭ দিনের রিভিশন রুটিন", "পরীক্ষার হলে সময় ভাগ করবেন যেভাবে", "সৃজনশীল প্রশ্নের উত্তর লেখার নিয়ম"]),
            ("pdf", "পরীক্ষার আগের চেকলিস্ট", PDF),
            ("pdf", "শেষ মুহূর্তের রিভিশন শিট", PDF),
        ],
    ),
    (
        "মোটিভেশন",
        "আইসিটি নিয়ে ভয় নয়",
        "যারা আইসিটিকে কঠিন মনে করেন, তাদের জন্য কিছু কথা।",
        None,
        None,
        videos(MOTIVATION),
    ),
    (
        "সাজেশন",
        "এইচএসসি আইসিটি ফাইনাল সাজেশন",
        "অধ্যায়ভিত্তিক গুরুত্বপূর্ণ প্রশ্ন — কোর্সের শিক্ষার্থীদের জন্য।",
        "hsc",
        STUDENTS_ONLY,
        [
            *[("pdf", f"অধ্যায় {n}: {chapter} — সাজেশন", PDF) for n, chapter in zip("১২৩৪৫৬", CHAPTERS, strict=True)],
            ("link", "বিগত বছরের প্রশ্ন (ওয়েবসাইট)", "https://www.w3schools.com/"),
        ],
    ),
    (
        "সাজেশন",
        "এসএসসি আইসিটি শর্ট সাজেশন",
        "এসএসসি পরীক্ষার্থীদের জন্য সংক্ষিপ্ত সাজেশন, সবার জন্য ফ্রি।",
        "ssc",
        None,
        [
            ("pdf", "এসএসসি আইসিটি শর্ট সাজেশন", PDF),
            ("video", "এসএসসি আইসিটি: শেষ মুহূর্তের প্রস্তুতি", VIDEOS[1]),
        ],
    ),
    (
        "নোট ও শিট",
        "অধ্যায়ভিত্তিক লেকচার শিট",
        "ক্লাসের লেকচার শিট, প্রতিটি অধ্যায়ের।",
        "hsc",
        None,
        [("pdf", f"লেকচার শিট — অধ্যায় {n}: {chapter}", PDF) for n, chapter in zip("১২৩৪৫৬", CHAPTERS, strict=True)]
        + [("pdf", f"অনুশীলনী শিট {n}", PDF) for n in "১২৩৪৫৬"],
    ),
    (
        "দরকারি লিংক",
        "প্র্যাকটিসের ওয়েবসাইট",
        "HTML আর প্রোগ্রামিং নিজে হাতে চর্চা করার জন্য।",
        None,
        None,
        [
            ("link", "HTML শেখা ও চর্চা (W3Schools)", "https://www.w3schools.com/html/"),
            ("link", "C প্রোগ্রামিং অনলাইনে চালান", "https://www.programiz.com/c-programming/online-compiler/"),
            ("link", "সংখ্যা পদ্ধতি রূপান্তর ক্যালকুলেটর", "https://www.rapidtables.com/convert/number/"),
            ("link", "লজিক গেট সিমুলেটর", "https://academo.org/demos/logic-gate-simulator/"),
        ],
    ),
]


class Command(BaseCommand):
    help = "Replace the example study material; local testing only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Only remove the example study material.")

    def handle(self, *args, clear=False, **options):
        names = [name for name, _ in CATEGORIES]
        BookOrder.objects.filter(item__topic__category__name__in=names).update(item=None)
        MaterialTopic.objects.filter(category__name__in=names).delete()
        MaterialCategory.objects.filter(name__in=names).delete()
        if clear:
            self.stdout.write("Example study material removed.")
            return

        categories = {
            name: MaterialCategory.objects.create(name=name, icon=icon, order=order)
            for order, (name, icon) in enumerate(CATEGORIES)
        }
        item_count = 0
        for order, (category, title, description, level, course, items) in enumerate(TOPICS):
            topic = MaterialTopic.objects.create(
                category=categories[category],
                title=title,
                description=description,
                class_level=ClassLevel.objects.filter(slug=level).first() if level else None,
                access=MaterialTopic.Access.ENROLLED if course else MaterialTopic.Access.FREE,
                is_published=True,
                order=order,
            )
            if course:
                topic.courses.set(Course.objects.filter(slug=course))
            for position, (kind, item_title, url, *extra) in enumerate(items):
                MaterialItem.objects.create(
                    topic=topic,
                    kind=kind,
                    title=item_title,
                    url=url,
                    order=position,
                    preview_url=PDF if kind == "book" else "",
                    **(extra[0] if extra else {}),
                )
            item_count += len(items)
        self.stdout.write(
            self.style.SUCCESS(f"{len(CATEGORIES)} categories, {len(TOPICS)} topics and {item_count} items added.")
        )
