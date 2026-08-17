"""Populate the database with realistic demo content.

Everything the two frontends read on their public and admin screens gets a
row here: the homepage aggregate (`/api/home`), course catalogue with the
full section/content tree, the MCQ bank and exam results behind the ranking
pages, the shop, and enough orders spread across the year for the admin
dashboard's charts to draw something.

    python manage.py seed_demo            # idempotent top-up
    python manage.py seed_demo --fresh    # wipe demo rows first

Images are generated as PNGs into MEDIA_ROOT and referenced as absolute
`http://localhost:8000/media/...` URLs, which is the one local host both
`next.config.ts` files whitelist in `images.remotePatterns`.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.content.models import (
    Advertisement,
    EBook,
    Notice,
    NoticeCategory,
    Page,
    Testimonial,
)
from apps.support.models import ContactMessage
from apps.courses.models import (
    Content,
    CourseMaterial,
    Coupon,
    Course,
    CourseCategory,
    CoursePrice,
    Enrollment,
    Routine,
    Section,
)
from apps.assessment.models import Exam, ExamAttempt, Question, QuestionBank
from apps.billing.models import Order, Payment
from apps.store.models import CartItem, Product
from apps.faculty.models import CourseInstructor, Teacher

User = get_user_model()

MEDIA_BASE = "http://localhost:8000/media"
SEED_DIR = "seed"

# Deterministic so re-running the command reproduces the same demo set.
RNG_SEED = 20260816

PALETTE = [
    ((14, 30, 65), (37, 99, 235)),
    ((49, 10, 62), (168, 85, 247)),
    ((5, 46, 42), (16, 185, 129)),
    ((66, 20, 10), (249, 115, 22)),
    ((48, 8, 24), (236, 72, 153)),
    ((10, 38, 56), (6, 182, 212)),
    ((40, 34, 4), (234, 179, 8)),
    ((26, 10, 52), (99, 102, 241)),
]


# ---------------------------------------------------------------------------
# Placeholder image generation
# ---------------------------------------------------------------------------


def _draw_placeholder(path, width, height, label, palette_index):
    """Diagonal-gradient PNG with a short ASCII label. The bundled default
    font has no Bangla glyphs, so labels stay in ASCII even though the demo
    content itself is Bangla."""
    from PIL import Image, ImageDraw, ImageFont

    top, bottom = PALETTE[palette_index % len(PALETTE)]
    image = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(image)

    steps = max(width, height)
    for i in range(steps):
        ratio = i / max(steps - 1, 1)
        color = tuple(int(top[c] + (bottom[c] - top[c]) * ratio) for c in range(3))
        draw.line([(i, 0), (0, i)], fill=color, width=2)

    try:
        font = ImageFont.load_default(size=max(18, height // 9))
    except TypeError:  # Pillow < 10.1 has a fixed-size default font
        font = ImageFont.load_default()

    box = draw.textbbox((0, 0), label, font=font)
    draw.text(
        ((width - (box[2] - box[0])) / 2, (height - (box[3] - box[1])) / 2),
        label,
        fill=(255, 255, 255),
        font=font,
    )
    image.save(path, "PNG")


def make_image(name, width, height, label, palette_index=0):
    """Write `media/seed/<name>.png` once and return its absolute URL."""
    from django.conf import settings

    directory = settings.MEDIA_ROOT / SEED_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.png"
    if not path.exists():
        _draw_placeholder(path, width, height, label, palette_index)
    return f"{MEDIA_BASE}/{SEED_DIR}/{name}.png"


# ---------------------------------------------------------------------------
# Demo content
# ---------------------------------------------------------------------------

# Slugs are supplied explicitly throughout: the models' `unique_slugify`
# runs Django's `slugify()`, which strips Bangla entirely and would collapse
# every row to "item", "item-2", ... — unusable as public URLs.
CATEGORIES = [
    ("এইচএসসি আইসিটি", "hsc-ict", [("এইচএসসি ২০২৬", "hsc-2026"), ("এইচএসসি ২০২৭", "hsc-2027")]),
    ("এসএসসি আইসিটি", "ssc-ict", [("এসএসসি ২০২৬", "ssc-2026")]),
    ("অ্যাডমিশন প্রস্তুতি", "admission", [("ভার্সিটি ক", "varsity-ka"), ("মেডিকেল", "medical")]),
    ("প্রোগ্রামিং", "programming", [("সি প্রোগ্রামিং", "c-programming"),
                                    ("ওয়েব ডিজাইন", "web-design")]),
]

# (title, slug, subtitle, category, duration, featured, is_online, chapters)
COURSES = [
    (
        "এইচএসসি আইসিটি ফুল কোর্স ২০২৬",
        "hsc-ict-full-course-2026",
        "৬ অধ্যায়ের সম্পূর্ণ সিলেবাস, বোর্ড প্রশ্ন সমাধান ও লাইভ ক্লাস",
        "এইচএসসি আইসিটি",
        "৬ মাস",
        True,
        True,
        [
            "তথ্য ও যোগাযোগ প্রযুক্তি: বিশ্ব ও বাংলাদেশ প্রেক্ষিত",
            "কমিউনিকেশন সিস্টেমস ও নেটওয়ার্কিং",
            "সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস",
            "এইচটিএমএল ও ওয়েব ডিজাইন",
            "প্রোগ্রামিং ভাষা (সি)",
            "ডেটাবেজ ম্যানেজমেন্ট সিস্টেম",
        ],
    ),
    (
        "সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস ক্র্যাশ কোর্স",
        "number-system-digital-device-crash",
        "তৃতীয় অধ্যায়ের গাণিতিক সমস্যা ও লজিক গেট শর্টকাট",
        "এইচএসসি আইসিটি",
        "৬ সপ্তাহ",
        True,
        True,
        ["সংখ্যা পদ্ধতি রূপান্তর", "বুলিয়ান অ্যালজেবরা", "লজিক গেট ও সার্কিট"],
    ),
    (
        "সি প্রোগ্রামিং জিরো টু হিরো",
        "c-programming-zero-to-hero",
        "শূন্য থেকে শুরু করে বোর্ড ও ভার্সিটি লেভেল প্রোগ্রামিং",
        "প্রোগ্রামিং",
        "৩ মাস",
        True,
        True,
        ["সি এর বেসিক", "কন্ট্রোল স্টেটমেন্ট", "অ্যারে ও ফাংশন"],
    ),
    (
        "এইচটিএমএল ও ওয়েব ডিজাইন মাস্টারক্লাস",
        "html-web-design-masterclass",
        "হাতে-কলমে ওয়েবসাইট তৈরি করে চতুর্থ অধ্যায় শেষ",
        "প্রোগ্রামিং",
        "৮ সপ্তাহ",
        True,
        True,
        ["এইচটিএমএল ট্যাগ পরিচিতি", "টেবিল, ফর্ম ও লিস্ট", "সিএসএস দিয়ে ডিজাইন"],
    ),
    (
        "এসএসসি আইসিটি সম্পূর্ণ প্রস্তুতি",
        "ssc-ict-full-preparation",
        "এসএসসি সিলেবাস অনুযায়ী অধ্যায়ভিত্তিক ক্লাস ও পরীক্ষা",
        "এসএসসি আইসিটি",
        "৪ মাস",
        True,
        True,
        ["তথ্য ও যোগাযোগ প্রযুক্তি", "কম্পিউটার ও যন্ত্রাংশ", "ইন্টারনেট ও ই-মেইল"],
    ),
    (
        "ভার্সিটি ভর্তি আইসিটি ফাইনাল রিভিশন",
        "admission-ict-final-revision",
        "ঢাবি, রাবি ও গুচ্ছ ভর্তি পরীক্ষার প্রশ্নব্যাংক সমাধান",
        "অ্যাডমিশন প্রস্তুতি",
        "১০ সপ্তাহ",
        False,
        True,
        ["গুরুত্বপূর্ণ সূত্র রিভিশন", "প্রশ্নব্যাংক সমাধান", "ফাইনাল মডেল টেস্ট"],
    ),
]

COURSE_FEATURES = [
    "৳ এককালীন পেমেন্ট, আজীবন এক্সেস",
    "প্রতিটি অধ্যায়ে লাইভ ক্লাস ও রেকর্ডিং",
    "অধ্যায়ভিত্তিক এমসিকিউ পরীক্ষা ও র‍্যাঙ্কিং",
    "পিডিএফ লেকচার শিট ও হ্যান্ডনোট",
    "২৪/৭ সাপোর্ট গ্রুপ",
]

TEACHERS = [
    ("রাহাদ স্যার", "প্রতিষ্ঠাতা ও প্রধান পরিচালক", "founder",
     "১২ বছরের বেশি সময় ধরে এইচএসসি আইসিটি পড়াচ্ছেন। ৫০,০০০+ শিক্ষার্থীর প্রিয় শিক্ষক।"),
    ("তানভীর হাসান", "সিনিয়র ইন্সট্রাক্টর, প্রোগ্রামিং", "instructor",
     "বুয়েট সিএসই থেকে স্নাতক। সি ও পাইথন প্রোগ্রামিং এর ক্লাস নেন।"),
    ("নুসরাত জাহান", "ইন্সট্রাক্টর, ওয়েব ডিজাইন", "instructor",
     "ফ্রন্টএন্ড ডেভেলপার ও শিক্ষক। এইচটিএমএল, সিএসএস ও ওয়েব ডিজাইন অধ্যায় পড়ান।"),
    ("সাইফুল ইসলাম", "ইন্সট্রাক্টর, ডেটাবেজ", "instructor",
     "ঢাকা বিশ্ববিদ্যালয়ের আইআইটি থেকে স্নাতকোত্তর। ডেটাবেজ ও নেটওয়ার্কিং পড়ান।"),
]

TESTIMONIALS = [
    ("সাদিয়া আফরিন", "এইচএসসি ২০২৫, ভিকারুননিসা নূন কলেজ", 5,
     "আইসিটি সবচেয়ে ভয়ের সাবজেক্ট ছিল। রাহাদ স্যারের ক্লাস করে বোর্ডে এ প্লাস পেয়েছি।"),
    ("মেহেদী হাসান", "এইচএসসি ২০২৫, নটর ডেম কলেজ", 5,
     "সংখ্যা পদ্ধতির অংক এত সহজে বুঝিয়ে দেওয়ার কারণে পরীক্ষায় একটাও ভুল হয়নি।"),
    ("ফারহানা ইয়াসমিন", "এইচএসসি ২০২৪, রাজশাহী কলেজ", 4,
     "লাইভ ক্লাসের রেকর্ডিং যেকোনো সময় দেখা যায়, এটাই সবচেয়ে বড় সুবিধা।"),
    ("আরিফুল ইসলাম", "ভর্তি পরীক্ষার্থী, ঢাকা", 5,
     "প্রশ্নব্যাংক সমাধানের ক্লাসগুলো ভর্তি পরীক্ষায় অনেক কাজে দিয়েছে।"),
    ("তাসনিম রহমান", "এসএসসি ২০২৫, ঢাকা", 5,
     "প্রতিটি অধ্যায় শেষে পরীক্ষা হওয়ায় নিজের দুর্বলতা ধরতে পেরেছি।"),
    ("রাকিবুল হাসান", "এইচএসসি ২০২৬, চট্টগ্রাম কলেজ", 4,
     "পিডিএফ শিটগুলো খুব গোছানো, আলাদা করে নোট করার দরকার হয় না।"),
]

NOTICE_CATEGORIES = [
    ("পরীক্ষা", "exam"),
    ("ক্লাস রুটিন", "class-routine"),
    ("ভর্তি বিজ্ঞপ্তি", "admission-notice"),
    ("সাধারণ", "general"),
]

NOTICES = [
    ("এইচএসসি ২০২৬ ব্যাচের ভর্তি চলছে", "hsc-2026-admission-open", "পরীক্ষা",
     "এইচএসসি ২০২৬ ব্যাচের আইসিটি ফুল কোর্সে ভর্তি চলছে। আসন সংখ্যা সীমিত, আগে আসলে আগে পাবেন ভিত্তিতে ভর্তি নেওয়া হচ্ছে।"),
    ("তৃতীয় অধ্যায়ের মডেল টেস্টের সময়সূচি", "model-test-schedule-chapter-3", "পরীক্ষা",
     "আগামী শুক্রবার রাত ৯টায় সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস অধ্যায়ের মডেল টেস্ট অনুষ্ঠিত হবে। মোট ৩০টি এমসিকিউ, সময় ২০ মিনিট।"),
    ("নতুন ক্লাস রুটিন প্রকাশিত", "new-class-routine-published", "ক্লাস রুটিন",
     "চলতি মাসের নতুন ক্লাস রুটিন প্রকাশ করা হয়েছে। প্রতি রবি, মঙ্গল ও বৃহস্পতিবার রাত ৮টায় লাইভ ক্লাস হবে।"),
    ("ঈদের ছুটিতে ক্লাস বন্ধ থাকবে", "eid-holiday-class-closed", "সাধারণ",
     "ঈদুল আজহা উপলক্ষে পাঁচ দিন লাইভ ক্লাস বন্ধ থাকবে। তবে রেকর্ডেড ক্লাস ও পরীক্ষা যথারীতি চালু থাকবে।"),
    ("ভার্সিটি ভর্তি ব্যাচের ফ্রি সেমিনার", "free-admission-seminar", "ভর্তি বিজ্ঞপ্তি",
     "ভর্তি পরীক্ষায় আইসিটি থেকে সর্বোচ্চ নম্বর তোলার কৌশল নিয়ে ফ্রি সেমিনার। রেজিস্ট্রেশন করে অংশ নিন।"),
    ("লেকচার শিট ডাউনলোড চালু হয়েছে", "lecture-sheet-download-live", "সাধারণ",
     "সকল ভর্তিকৃত শিক্ষার্থী এখন কোর্সের ভেতর থেকে অধ্যায়ভিত্তিক পিডিএফ লেকচার শিট ডাউনলোড করতে পারবেন।"),
]

EBOOKS = [
    ("আইসিটি সূত্র সমগ্র", "এক নজরে ছয় অধ্যায়ের সব সূত্র ও শর্টকাট টেকনিক।"),
    ("বোর্ড প্রশ্নব্যাংক ২০১৭-২০২৫", "সকল বোর্ডের এমসিকিউ ও সৃজনশীল প্রশ্নের সমাধানসহ সংকলন।"),
    ("সি প্রোগ্রামিং হ্যান্ডনোট", "সিনট্যাক্স, লুপ ও ফাংশনের সহজ ব্যাখ্যা ও উদাহরণ।"),
]

# `discount` is the amount OFF, the same as CoursePrice.discount and what
# `product_price_after_discount` subtracts. These used to hold the sale price
# instead — 450/380 — which is the opposite meaning for the same field name.
PRODUCTS = [
    ("আইসিটি ডাইজেস্ট (প্রিন্ট কপি)", "ict-digest-print", Decimal("450"), Decimal("70"), 120,
     "এইচএসসি আইসিটির সম্পূর্ণ সিলেবাস কভার করা প্রিন্টেড ডাইজেস্ট বই।"),
    ("সংখ্যা পদ্ধতি প্র্যাকটিস বুক", "number-system-practice-book", Decimal("250"), Decimal("51"), 85,
     "৫০০+ অনুশীলন সমস্যা ও ধাপে ধাপে সমাধান।"),
    ("বোর্ড প্রশ্নব্যাংক সমাধান", "board-question-bank-solution", Decimal("380"), None, 60,
     "গত ৯ বছরের সকল বোর্ড প্রশ্নের সমাধান একসাথে।"),
    ("সি প্রোগ্রামিং ওয়ার্কবুক", "c-programming-workbook", Decimal("320"), Decimal("50"), 45,
     "হাতে-কলমে কোড লিখে শেখার ওয়ার্কবুক।"),
    ("লজিক গেট পোস্টার সেট", "logic-gate-poster-set", Decimal("180"), None, 200,
     "পড়ার টেবিলের জন্য লেমিনেটেড লজিক গেট ও ট্রুথ টেবিল পোস্টার।"),
    ("এসএসসি আইসিটি গাইড", "ssc-ict-guide", Decimal("300"), Decimal("45"), 70,
     "এসএসসি সিলেবাস অনুযায়ী অধ্যায়ভিত্তিক গাইড বই।"),
]

STUDENT_NAMES = [
    "সাদিয়া আফরিন", "মেহেদী হাসান", "ফারহানা ইয়াসমিন", "আরিফুল ইসলাম",
    "তাসনিম রহমান", "রাকিবুল হাসান", "নুসরাত জাহান", "সাইফুল ইসলাম",
    "জান্নাতুল ফেরদৌস", "শাহরিয়ার কবির", "মাহমুদা খাতুন", "ইমরান হোসেন",
    "সুমাইয়া আক্তার", "তানভীর আহমেদ", "রুবাইয়া ইসলাম", "নাফিস ইকবাল",
    "লামিয়া চৌধুরী", "আসিফ মাহমুদ", "সানজিদা পারভীন", "হাসিবুল হক",
    "মারিয়া তাবাসসুম", "রায়হান কবির", "অন্তরা দাস", "সৌরভ মজুমদার",
    "ইশরাত জাহান",
]

INSTITUTIONS = [
    "ঢাকা কলেজ", "নটর ডেম কলেজ", "ভিকারুননিসা নূন কলেজ", "রাজশাহী কলেজ",
    "চট্টগ্রাম কলেজ", "আদমজী ক্যান্টনমেন্ট কলেজ", "সরকারি বিজ্ঞান কলেজ",
]

# (question, a, b, c, d, answer, explanation)
MCQ_BANK = [
    ("(১১০১)₂ সংখ্যাটির দশমিক মান কত?", "১১", "১৩", "১৫", "৯", "b",
     "১×৮ + ১×৪ + ০×২ + ১×১ = ১৩"),
    ("১ কিলোবাইট সমান কত বাইট?", "১০০০", "১০২৪", "৫১২", "২০৪৮", "b",
     "২^১০ = ১০২৪ বাইট।"),
    ("কোনটি ইউনিভার্সাল গেট?", "AND", "OR", "NAND", "XOR", "c",
     "NAND ও NOR দিয়ে সব ধরনের গেট তৈরি করা যায়।"),
    ("ASCII কোডে অক্ষর সংখ্যা কত বিটে প্রকাশ করা হয়?", "৪", "৭", "৮", "১৬", "b",
     "স্ট্যান্ডার্ড ASCII ৭ বিটের কোড।"),
    ("হেক্সাডেসিমেল সংখ্যা পদ্ধতির ভিত্তি কত?", "৮", "১০", "১২", "১৬", "d",
     "হেক্সাডেসিমেলের বেজ ১৬।"),
    ("HTML এ সবচেয়ে বড় হেডিং ট্যাগ কোনটি?", "<h1>", "<h6>", "<head>", "<big>", "a",
     "<h1> সবচেয়ে বড় এবং <h6> সবচেয়ে ছোট হেডিং।"),
    ("ওয়েবপেজে ছবি যুক্ত করার ট্যাগ কোনটি?", "<image>", "<img>", "<picture>", "<src>", "b",
     "<img src=\"...\"> ট্যাগ দিয়ে ছবি যুক্ত করা হয়।"),
    ("সি ভাষায় প্রোগ্রাম কার্যকর হওয়া শুরু হয় কোন ফাংশন থেকে?", "start()", "begin()", "main()", "run()", "c",
     "প্রতিটি সি প্রোগ্রাম main() ফাংশন থেকে শুরু হয়।"),
    ("কোনটি লুপ কন্ট্রোল স্টেটমেন্ট নয়?", "for", "while", "do-while", "switch", "d",
     "switch একটি ডিসিশন কন্ট্রোল স্টেটমেন্ট, লুপ নয়।"),
    ("ডেটাবেজে প্রাইমারি কী এর বৈশিষ্ট্য কোনটি?", "নাল হতে পারে", "একাধিক থাকতে পারে",
     "ইউনিক ও নাল নয়", "সবগুলো", "c",
     "প্রাইমারি কী অবশ্যই ইউনিক হবে এবং নাল হতে পারবে না।"),
    ("LAN এর পূর্ণরূপ কী?", "Local Area Network", "Long Area Network",
     "Linked Access Node", "Logical Area Network", "a", "LAN = Local Area Network।"),
    ("কোন ট্রান্সমিশন মোডে একসাথে দুই দিকে ডেটা যায়?", "সিমপ্লেক্স", "হাফ-ডুপ্লেক্স",
     "ফুল-ডুপ্লেক্স", "মাল্টিকাস্ট", "c",
     "ফুল-ডুপ্লেক্সে একই সময়ে উভয় দিকে ডেটা আদান-প্রদান হয়।"),
    ("অপটিক্যাল ফাইবারে ডেটা পরিবহন হয় কীসের মাধ্যমে?", "তড়িৎ প্রবাহ", "আলোক সংকেত",
     "রেডিও তরঙ্গ", "মাইক্রোওয়েভ", "b",
     "অপটিক্যাল ফাইবারে আলোর পূর্ণ অভ্যন্তরীণ প্রতিফলনে ডেটা যায়।"),
    ("বায়োমেট্রিক্সের উদাহরণ কোনটি?", "পাসওয়ার্ড", "ফিঙ্গারপ্রিন্ট", "ওটিপি", "পিন", "b",
     "ফিঙ্গারপ্রিন্ট একটি শারীরবৃত্তীয় বায়োমেট্রিক বৈশিষ্ট্য।"),
    ("ন্যানো টেকনোলজির একক কত?", "১০^-৬ মিটার", "১০^-৯ মিটার", "১০^-১২ মিটার", "১০^-৩ মিটার", "b",
     "১ ন্যানোমিটার = ১০^-৯ মিটার।"),
]

STATIC_PAGES = [
    # The client requests this key literally (see the web app's about page).
    ("about", "html",
     "<h2>আমাদের সম্পর্কে</h2><p>শমাধান কোচিং দেশের যেকোনো প্রান্তের শিক্ষার্থীর কাছে "
     "মানসম্মত আইসিটি শিক্ষা পৌঁছে দেওয়ার লক্ষ্যে কাজ করছে। ২০১৮ সাল থেকে এখন পর্যন্ত "
     "৫০ হাজারের বেশি শিক্ষার্থী আমাদের কোর্সে যুক্ত হয়েছেন।</p>"),
    ("our-goal", "html",
     "<h2>আমাদের লক্ষ্য</h2><p>প্রতিটি শিক্ষার্থী যেন আইসিটি বিষয়ে আত্মবিশ্বাসের সাথে "
     "পরীক্ষা দিতে পারে এবং বাস্তব জীবনে প্রযুক্তি ব্যবহার করতে শেখে — এটাই আমাদের লক্ষ্য।</p>"),
    ("terms-and-conditions", "html",
     "<h2>শর্তাবলি</h2><p>কোর্সে ভর্তির পর ফি ফেরতযোগ্য নয়। একটি অ্যাকাউন্ট শুধু একজন "
     "শিক্ষার্থী ব্যবহার করতে পারবেন। ক্লাসের ভিডিও রেকর্ড বা বিতরণ করা সম্পূর্ণ নিষিদ্ধ।</p>"),
    ("privacy-policy", "html",
     "<h2>গোপনীয়তা নীতি</h2><p>আমরা শিক্ষার্থীর নাম, মোবাইল নম্বর ও প্রতিষ্ঠানের তথ্য "
     "শুধুমাত্র কোর্স পরিচালনার জন্য সংগ্রহ করি এবং তৃতীয় পক্ষের সাথে শেয়ার করি না।</p>"),
    ("refund-policy", "html",
     "<h2>রিফান্ড নীতি</h2><p>ভুল পেমেন্টের ক্ষেত্রে ৭ কার্যদিবসের মধ্যে আবেদন করলে "
     "যাচাই সাপেক্ষে অর্থ ফেরত দেওয়া হয়।</p>"),
    ("contact-info", "html",
     "<h2>যোগাযোগ</h2><p>মোবাইল: ০১৭১১৭৭৮৬০২<br/>ইমেইল: support@shomadhan.local<br/>"
     "ঠিকানা: ১২/এ, গ্রীন রোড, ঢাকা ১২০৫</p>"),
]

CONTACT_MESSAGES = [
    ("কোর্সে ভর্তি হতে চাই", "এইচএসসি ২০২৬ ব্যাচে ভর্তি হতে চাই। পেমেন্ট কীভাবে করব?"),
    ("ভিডিও চলছে না", "তৃতীয় অধ্যায়ের ২য় ক্লাসের ভিডিও লোড হচ্ছে না। একটু দেখবেন?"),
    ("পিডিএফ ডাউনলোড", "লেকচার শিট ডাউনলোড করতে পারছি না, বাটনে ক্লিক করলে কিছু হয় না।"),
    ("রুটিন জানতে চাই", "আগামী সপ্তাহের লাইভ ক্লাসের সময়সূচি কোথায় পাব?"),
    ("পেমেন্ট কনফার্ম হয়নি", "বিকাশে টাকা পাঠিয়েছি কিন্তু কোর্স এখনো চালু হয়নি।"),
]


class Command(BaseCommand):
    help = "Seed the database with demo content for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--fresh",
            action="store_true",
            help="Delete existing demo rows (and demo students) before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.rng = random.Random(RNG_SEED)
        self.now = timezone.now()

        if options["fresh"]:
            self._wipe()

        self._seed_pages()
        categories = self._seed_categories()
        teachers = self._seed_teachers()
        self._seed_testimonials()
        self._seed_advertisements()
        self._seed_notices()
        self._seed_ebooks()
        stores = self._seed_mcq_bank()
        courses = self._seed_courses(categories, teachers, stores)
        products = self._seed_products(categories)
        students = self._seed_students()
        self._seed_enrollments(courses, students)
        self._seed_orders(courses, products, students)
        self._seed_exam_results(courses, students)
        self._seed_contact_messages(students)
        self._seed_materials(courses)

        self.stdout.write(self.style.SUCCESS("\nDemo data ready:"))
        for label, count in [
            ("course categories", CourseCategory.objects.count()),
            ("courses", Course.objects.count()),
            ("sections", Section.objects.count()),
            ("contents", Content.objects.count()),
            ("mcq questions", Question.objects.count()),
            ("teachers", Teacher.objects.count()),
            ("testimonials", Testimonial.objects.count()),
            ("notices", Notice.objects.count()),
            ("products", Product.objects.count()),
            ("students", User.objects.filter(role=User.Role.STUDENT).count()),
            ("enrollments", Enrollment.objects.count()),
            ("orders", Order.objects.count()),
            ("payments", Payment.objects.count()),
            ("exam results", ExamAttempt.objects.count()),
        ]:
            self.stdout.write(f"  {count:>5}  {label}")
        self.stdout.write(
            "\nStudent logins: phone 01810000001 … 01810000025, password student1234"
        )

    # -- wipe ---------------------------------------------------------------

    def _wipe(self):
        self.stdout.write("Removing existing demo rows...")
        for model in [
            Payment, Order, CartItem, ExamAttempt, Enrollment, Content, Section,
            Routine, Coupon, CoursePrice, CourseInstructor, Course, CourseCategory,
            Question, QuestionBank, Product, CourseMaterial, ContactMessage,
            Notice, NoticeCategory, EBook, Advertisement, Testimonial, Teacher,
        ]:
            model.objects.all().delete()
        User.objects.filter(role=User.Role.STUDENT, phone__startswith="0181").delete()
        Page.objects.exclude(
            key__in=["homeBannerImage", "homeCourseCounter", "homeStudentCounter",
                     "homeInstructorCounter"]
        ).delete()

    # -- cms ----------------------------------------------------------------

    def _seed_pages(self):
        banner = make_image("banner", 1600, 600, "SHOMADHAN", 0)
        counters = {
            "homeCourseCounter": "24",
            "homeStudentCounter": "52400",
            "homeInstructorCounter": "18",
        }
        for key, value in counters.items():
            Page.objects.update_or_create(
                key=key, defaults={"slug": key, "value_type": Page.ValueType.COUNTER,
                                   "value": value}
            )
        Page.objects.update_or_create(
            key="homeBannerImage",
            defaults={"slug": "homeBannerImage", "value_type": Page.ValueType.IMAGE,
                      "value": "", "image": banner},
        )
        for index, (key, value_type, value) in enumerate(STATIC_PAGES):
            Page.objects.update_or_create(
                key=key,
                defaults={"slug": key, "value_type": value_type, "value": value,
                          "image": make_image(f"page-{key}", 1200, 630, key.upper()[:12],
                                              index + 1)},
            )
        self.stdout.write("  pages + homepage counters")

    def _seed_categories(self):
        categories = {}
        for index, (title, slug, children) in enumerate(CATEGORIES):
            parent, _ = CourseCategory.objects.get_or_create(
                slug=slug,
                defaults={"title": title, "category": None, "order": index,
                          "image": make_image(f"cat-{index}", 600, 400, f"CAT {index + 1}", index)},
            )
            categories[title] = parent
            for child_index, (child_title, child_slug) in enumerate(children):
                CourseCategory.objects.get_or_create(
                    slug=child_slug,
                    defaults={"title": child_title, "category": parent, "order": child_index,
                              "image": make_image(f"cat-{index}-{child_index}", 600, 400,
                                                  f"SUB {child_index + 1}", index + 2)},
                )
        self.stdout.write("  course categories")
        return categories

    def _seed_teachers(self):
        teachers = []
        for index, (name, designation, kind, description) in enumerate(TEACHERS):
            teacher, _ = Teacher.objects.get_or_create(
                name=name,
                defaults={"designation": designation, "type": kind,
                          "description": description, "order": index,
                          "image": make_image(f"teacher-{index}", 500, 500,
                                              f"T{index + 1}", index + 3)},
            )
            teachers.append(teacher)
        self.stdout.write("  teachers")
        return teachers

    def _seed_testimonials(self):
        for index, (name, designation, rating, text) in enumerate(TESTIMONIALS):
            Testimonial.objects.get_or_create(
                name=name,
                defaults={"designation": designation, "ratings": rating,
                          "description": text,
                          "image": make_image(f"student-{index}", 400, 400,
                                              f"S{index + 1}", index)},
            )
        self.stdout.write("  testimonials")

    def _seed_advertisements(self):
        ads = [
            ("এইচএসসি ২০২৬ ব্যাচে ভর্তি চলছে", "৪০% ছাড়ে ভর্তি হওয়ার শেষ সুযোগ", "banner"),
            ("ফ্রি মডেল টেস্ট সিরিজ", "রেজিস্ট্রেশন করেই অংশ নিন সাপ্তাহিক মডেল টেস্টে", "sidebar"),
        ]
        for index, (title, description, kind) in enumerate(ads):
            Advertisement.objects.get_or_create(
                title=title,
                defaults={"description": description, "type": kind,
                          "link": "http://localhost:3000/course",
                          "image": make_image(f"ad-{index}", 1200, 400,
                                              f"AD {index + 1}", index + 1)},
            )
        self.stdout.write("  advertisements")

    def _seed_notices(self):
        categories = {}
        for index, (title, slug) in enumerate(NOTICE_CATEGORIES):
            category, _ = NoticeCategory.objects.get_or_create(
                slug=slug,
                defaults={"title": title, "notice_category": None, "order": index},
            )
            categories[title] = category

        for index, (title, slug, category_title, body) in enumerate(NOTICES):
            notice, created = Notice.objects.get_or_create(
                slug=slug,
                defaults={"title": title, "body": body,
                          "image": make_image(f"notice-{index}", 900, 500,
                                              f"NOTICE {index + 1}", index + 2)},
            )
            if created:
                notice.categories.add(categories[category_title])
                # Spread notices back through the last few weeks so the list
                # is not a single timestamp.
                Notice.objects.filter(pk=notice.pk).update(
                    created_at=self.now - timedelta(days=index * 5 + 1)
                )
        self.stdout.write("  notices")

    def _seed_ebooks(self):
        for index, (title, description) in enumerate(EBOOKS):
            EBook.objects.get_or_create(
                title=title,
                defaults={"description": description,
                          "booking_link": "http://localhost:3000/contact",
                          "preview": f"{MEDIA_BASE}/{SEED_DIR}/ebook-{index}.png",
                          "image": make_image(f"ebook-{index}", 600, 800,
                                              f"EBOOK {index + 1}", index + 4)},
            )
        self.stdout.write("  ebooks")

    # -- exams --------------------------------------------------------------

    def _seed_mcq_bank(self):
        root, _ = QuestionBank.objects.get_or_create(title="আইসিটি প্রশ্নব্যাংক",
                                                 parent=None, defaults={"order": 0})
        folders = ["সংখ্যা পদ্ধতি", "নেটওয়ার্কিং", "ওয়েব ডিজাইন", "সি প্রোগ্রামিং",
                   "ডেটাবেজ"]
        stores = []
        for index, title in enumerate(folders):
            store, _ = QuestionBank.objects.get_or_create(
                title=title, parent=root, defaults={"order": index}
            )
            stores.append(store)

        # Deal the shared question bank round-robin into the topic folders.
        for index, row in enumerate(MCQ_BANK):
            question, a, b, c, d, answer, explanation = row
            store = stores[index % len(stores)]
            Question.objects.get_or_create(
                bank=store,
                question=question,
                defaults={"a": a, "b": b, "c": c, "d": d, "answer": answer,
                          "explanation": explanation, "source_subject": "আইসিটি",
                          "source_year": str(2019 + (index % 7)),
                          "source_board": ["ঢাকা", "রাজশাহী", "চট্টগ্রাম", "যশোর"][index % 4],
                          "source_chapter": store.title},
            )
        self.stdout.write("  mcq bank")
        return stores

    # -- courses ------------------------------------------------------------

    def _seed_courses(self, categories, teachers, stores):
        courses = []
        for index, row in enumerate(COURSES):
            title, slug, subtitle, category_title, duration, featured, is_online, chapters = row
            course, created = Course.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "subtitle": subtitle,
                    "duration": duration,
                    "featured": featured,
                    "is_online": is_online,
                    "active": True,
                    "fake_user_count": self.rng.randint(400, 4200),
                    "description": (
                        f"<p>{subtitle}</p><p>কোর্সটিতে মোট {len(chapters)}টি অধ্যায় রয়েছে। "
                        "প্রতিটি অধ্যায়ে থাকছে রেকর্ডেড ভিডিও ক্লাস, লেকচার শিট, "
                        "অধ্যায়ভিত্তিক এমসিকিউ পরীক্ষা এবং লাইভ প্রশ্নোত্তর সেশন।</p>"
                    ),
                    "features": COURSE_FEATURES,
                    "video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "image": make_image(f"course-{index}", 800, 450,
                                        f"COURSE {index + 1}", index),
                },
            )
            if created:
                course.categories.add(categories[category_title])
                self._seed_course_prices(course, index)
                self._seed_course_extras(course, teachers, index)
                self._seed_course_tree(course, chapters, stores, index, slug)
            courses.append(course)
        self.stdout.write("  courses + sections + contents")
        return courses

    def _seed_course_prices(self, course, index):
        base = Decimal(str(1500 + index * 500))
        full = CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=course.id,
            title="ফুল কোর্স (আজীবন এক্সেস)",
            amount=base,
            # `discount` is the amount OFF, which is what `price_after_discount`
            # subtracts and what billing's own test asserts (1500 - 300 = 1200).
            # This used to seed `base - 300`, i.e. 1200 against a 1500 course,
            # so the API quoted — and would have charged — 300 for a 1500 taka
            # course, and the storefront correctly displayed an 80% discount.
            discount=Decimal("300") if index % 2 == 0 else None,
            discount_till=self.now + timedelta(days=30),
            type=CoursePrice.Type.FULL,
            validity_type=CoursePrice.ValidityType.RELATIVE,
            validity_duration=365,
        )
        CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=course.id,
            title="মাসিক সাবস্ক্রিপশন",
            amount=(base / Decimal("5")).quantize(Decimal("1")),
            type=CoursePrice.Type.SUBSCRIPTION,
            validity_type=CoursePrice.ValidityType.RELATIVE,
            validity_duration=30,
        )
        Coupon.objects.create(
            price=full,
            code=f"ICT{index + 1}0",
            discount=Decimal("10"),
            discount_type=Coupon.DiscountType.PERCENT,
            valid_till=self.now + timedelta(days=45),
        )

    def _seed_course_extras(self, course, teachers, index):
        teacher = teachers[index % len(teachers)]
        # Link to the roster teacher rather than copying its fields; the
        # model fills name/designation/description/image from it on save.
        CourseInstructor.objects.create(
            course=course,
            teacher=teacher,
            institute="শমাধান কোচিং",
            type=(CourseInstructor.Type.FOUNDER if teacher.type == "founder"
                  else CourseInstructor.Type.INSTRUCTOR),
            commission=Decimal("25.00"),
            email=f"instructor{index + 1}@shomadhan.local",
            phone=f"0171000{index + 1:04d}",
            order=0,
        )
        for routine_index, label in enumerate(["সাপ্তাহিক ক্লাস রুটিন", "পরীক্ষার সময়সূচি"]):
            Routine.objects.create(
                course=course,
                title=label,
                link=f"{MEDIA_BASE}/{SEED_DIR}/course-{index}.png",
            )

    def _seed_course_tree(self, course, chapters, stores, course_index, course_slug):
        """One section per chapter: video lessons, a lecture sheet, a note, a
        live class and a chapter exam wired to an MCQ folder."""
        for chapter_index, chapter in enumerate(chapters):
            chapter_slug = f"{course_slug}-ch{chapter_index + 1}"
            section = Section.objects.create(
                course=course, title=chapter, slug=chapter_slug,
                order=chapter_index, active=True,
            )
            order = 0

            for lesson_index in range(3):
                Content.objects.create(
                    course=course, section=section,
                    title=f"{chapter} — ক্লাস {lesson_index + 1}",
                    slug=f"{chapter_slug}-video-{lesson_index + 1}",
                    type=Content.Type.VIDEO,
                    variant=Content.Variant.NEW,
                    paid=not (chapter_index == 0 and lesson_index == 0),
                    order=order,
                    video_source="youtube",
                    video_link="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    video_description="ক্লাসটিতে অধ্যায়ের মূল ধারণা উদাহরণসহ আলোচনা করা হয়েছে।",
                    video_embedded=True,
                )
                order += 1

            Content.objects.create(
                course=course, section=section,
                title=f"{chapter} — লেকচার শিট",
                slug=f"{chapter_slug}-sheet",
                type=Content.Type.PDF, paid=True, order=order,
                pdf_file=f"{MEDIA_BASE}/{SEED_DIR}/course-{course_index}.png",
            )
            order += 1

            Content.objects.create(
                course=course, section=section,
                title=f"{chapter} — হ্যান্ডনোট",
                slug=f"{chapter_slug}-note",
                type=Content.Type.NOTE, paid=True, order=order,
                note_body=(
                    f"<h3>{chapter}</h3><ul>"
                    "<li>অধ্যায়ের গুরুত্বপূর্ণ সংজ্ঞা ও সূত্র</li>"
                    "<li>বোর্ড পরীক্ষায় বারবার আসা প্রশ্নের তালিকা</li>"
                    "<li>সাধারণ ভুল ও তা এড়ানোর কৌশল</li></ul>"
                ),
            )
            order += 1

            Content.objects.create(
                course=course, section=section,
                title=f"{chapter} — লাইভ প্রশ্নোত্তর",
                slug=f"{chapter_slug}-live",
                type=Content.Type.LIVE, paid=True, order=order,
                live_url="https://meet.google.com/demo-shomadhan",
                live_scheduled_at=self.now + timedelta(days=chapter_index * 3 + 2),
            )
            order += 1

            store = stores[(course_index + chapter_index) % len(stores)]
            exam_content = Content.objects.create(
                course=course, section=section,
                title=f"{chapter} — অধ্যায়ভিত্তিক পরীক্ষা",
                slug=f"{chapter_slug}-exam",
                type=Content.Type.EXAM, paid=True, order=order,
            )
            Exam.objects.create(
                content=exam_content,
                question_bank=store,
                mode=Exam.Mode.EXAM,
                total_marks=15,
                pass_marks=8,
                positive_marks=Decimal("1.00"),
                negative_marks=Decimal("0.25"),
                duration_minutes=15,
                start_time=self.now - timedelta(days=7),
                end_time=self.now + timedelta(days=30),
                result_publish_time=self.now - timedelta(days=6),
            )

    def _seed_materials(self, courses):
        for index, course in enumerate(courses[:4]):
            CourseMaterial.objects.get_or_create(
                title=f"{course.title} — সাপ্লিমেন্টারি শিট",
                defaults={"type": "pdf", "course": course,
                          "file": f"{MEDIA_BASE}/{SEED_DIR}/course-{index}.png"},
            )
        self.stdout.write("  course materials")

    # -- shop ---------------------------------------------------------------

    def _seed_products(self, categories):
        category = categories["এইচএসসি আইসিটি"]
        products = []
        for index, (name, slug, price, discount, stock, description) in enumerate(PRODUCTS):
            product, created = Product.objects.get_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "price": price, "discount": discount, "stock": stock,
                    "description": description,
                    "featured": index < 3,
                    "is_book": index != 4,
                    "sku": f"SHM-{index + 101}",
                    "order": index,
                    "discount_till": self.now + timedelta(days=20) if discount else None,
                    "image": make_image(f"product-{index}", 600, 600,
                                        f"BOOK {index + 1}", index + 2),
                },
            )
            if created:
                product.categories.add(category)
            products.append(product)
        self.stdout.write("  products")
        return products

    # -- users --------------------------------------------------------------

    def _seed_students(self):
        students = []
        for index, name in enumerate(STUDENT_NAMES):
            phone = f"0181000{index + 1:04d}"
            student = User.objects.filter(phone=phone).first()
            if student is None:
                joined = self.now - timedelta(days=self.rng.randint(3, 330))
                student = User.objects.create_user(
                    phone=phone,
                    email=f"student{index + 1}@shomadhan.local",
                    password="student1234",
                    name=name,
                    role=User.Role.STUDENT,
                    institution=INSTITUTIONS[index % len(INSTITUTIONS)],
                    educational_session=self.rng.choice(["২০২৪-২৫", "২০২৫-২৬", "২০২৬-২৭"]),
                    guardian_phone=f"0191000{index + 1:04d}",
                    phone_verified_at=joined,
                    date_joined=joined,
                    image=make_image(f"avatar-{index}", 300, 300, f"U{index + 1}", index),
                )
            students.append(student)
        self.stdout.write("  students")
        return students

    def _seed_enrollments(self, courses, students):
        for student in students:
            for course in self.rng.sample(courses, self.rng.randint(1, 3)):
                Enrollment.objects.get_or_create(
                    course=course, user=student,
                    defaults={"payment_type": Enrollment.PaymentType.PAID,
                              "valid_till": self.now + timedelta(days=365)},
                )
        self.stdout.write("  enrollments")

    def _seed_orders(self, courses, products, students):
        """Orders are back-dated across the last 12 months so the admin
        dashboard's sales-overview and payment charts have a series to plot.
        `created_at` is auto_now_add, so it is rewritten via queryset update."""
        if Order.objects.exists():
            self.stdout.write("  orders (already present, skipped)")
            return

        vendors = [Payment.Vendor.BKASH, Payment.Vendor.NAGAD, Payment.Vendor.ROCKET]
        for i in range(90):
            student = self.rng.choice(students)
            days_ago = self.rng.randint(0, 360)
            created = self.now - timedelta(days=days_ago,
                                           hours=self.rng.randint(0, 23))

            if self.rng.random() < 0.7:
                course = self.rng.choice(courses)
                # `prices` is ordered by amount, so `.first()` would always be
                # the cheap subscription tier — mix both so income varies.
                available = list(course.prices)
                if not available:
                    continue
                price = self.rng.choice(available)
                amount = price.discount or price.amount
                order_kwargs = {"course": course, "price": price,
                                "item_title": course.title, "price_title": price.title}
            else:
                product = self.rng.choice(products)
                amount = product.discount or product.price
                order_kwargs = {"product": product, "item_title": product.name,
                                "price_title": "একক ক্রয়"}

            status = self.rng.choices(
                [Order.Status.PAID, Order.Status.PENDING, Order.Status.CANCELLED],
                weights=[78, 15, 7],
            )[0]
            quantity = 1
            order = Order.objects.create(
                user=student, quantity=quantity, amount=amount,
                total=amount * quantity, status=status, **order_kwargs,
            )
            Order.objects.filter(pk=order.pk).update(created_at=created)

            payment_status = {
                Order.Status.PAID: Payment.Status.SUCCESSFUL,
                Order.Status.PENDING: Payment.Status.PENDING,
                Order.Status.CANCELLED: Payment.Status.FAILED,
            }[status]
            payment = Payment.objects.create(
                order=order, amount=amount,
                transaction_id=f"TRX{self.rng.randint(100000, 999999)}{i}",
                vendor=self.rng.choice(vendors),
                sent_from=student.phone,
                sent_to="01711778602",
                status=payment_status,
            )
            Payment.objects.filter(pk=payment.pk).update(created_at=created)
        self.stdout.write("  orders + payments")

    def _seed_exam_results(self, courses, students):
        """Fill the leaderboard behind /ranking/[id] for the first exam of the
        first few courses."""
        exams = Exam.objects.filter(
            content__type=Content.Type.EXAM, content__course__in=courses[:3]
        ).order_by("pk")[:4]

        for exam in exams:
            for student in self.rng.sample(students, 18):
                positive = Decimal(self.rng.randint(6, 15))
                negative = (Decimal(self.rng.randint(0, 4)) * Decimal("0.25"))
                ExamAttempt.objects.get_or_create(
                    exam=exam, user=student,
                    defaults={
                        "marks": positive - negative,
                        "positive_marks": positive,
                        "negative_marks": negative,
                        "duration": self.rng.randint(240, 900),
                        "submitted": True,
                        "answers": [],
                    },
                )
        self.stdout.write("  exam results")

    def _seed_contact_messages(self, students):
        for index, (subject, message) in enumerate(CONTACT_MESSAGES):
            student = students[index % len(students)]
            ContactMessage.objects.get_or_create(
                subject=subject, message=message,
                defaults={"user": student, "name": student.name,
                          "phone": student.phone, "email": student.email,
                          "is_read": index % 2 == 0},
            )
        self.stdout.write("  contact messages")
