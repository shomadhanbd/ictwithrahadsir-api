"""Populate the database with realistic demo content.

Covers what the public site and admin panel show: pages, the academic
taxonomy, the course catalogue with its section/content tree, notices,
students, enrolments, and a year of orders for the dashboard charts.

    python manage.py seed_demo            # idempotent top-up
    python manage.py seed_demo --fresh    # wipe demo rows first

Development only: `apps.demo` is installed by the local settings alone, and the
command refuses to run unless DEBUG is on and the database is SQLite (or
ALLOW_DEMO_SEED=1 is set for a disposable Postgres). `--fresh` empties whole tables.

Images are generated as PNGs into MEDIA_ROOT and referenced as absolute
`http://localhost:8000/media/...` URLs, which is the one local host both
`next.config.ts` files whitelist in `images.remotePatterns`.
"""

import os
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.academic.models import Batch, Chapter, ClassLevel, Group, Subject, Topic
from apps.billing.models import Payment, Product
from apps.content.models import (
    Advertisement,
    EBook,
    Notice,
    NoticeCategory,
    Page,
    Testimonial,
)
from apps.courses.models import (
    Content,
    Course,
    CourseMaterial,
    CourseTeacher,
    Enrollment,
    Routine,
    Section,
)
from apps.profiles.models import GuardianProfile, StudentProfile, TeacherProfile

User = get_user_model()

MEDIA_BASE = "http://localhost:8000/media"
SEED_DIR = "seed"

# Deterministic so re-running the command reproduces the same demo set.
RNG_SEED = 20260816


def teacher_phone(index):
    return f"0171000{index + 1:04d}"


def student_phone(index):
    return f"0181000{index + 1:04d}"


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
    directory = settings.MEDIA_ROOT / SEED_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.png"
    if not path.exists():
        _draw_placeholder(path, width, height, label, palette_index)
    return f"{MEDIA_BASE}/{SEED_DIR}/{name}.png"


# ---------------------------------------------------------------------------
# Demo content
# ---------------------------------------------------------------------------

# (title, slug, subtitle, duration, featured, is_online, chapters)
COURSES = [
    (
        "এইচএসসি আইসিটি ফুল কোর্স ২০২৬",
        "hsc-ict-full-course-2026",
        "৬ অধ্যায়ের সম্পূর্ণ সিলেবাস, বোর্ড প্রশ্ন সমাধান ও লাইভ ক্লাস",
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
        "৬ সপ্তাহ",
        True,
        True,
        ["সংখ্যা পদ্ধতি রূপান্তর", "বুলিয়ান অ্যালজেবরা", "লজিক গেট ও সার্কিট"],
    ),
    (
        "সি প্রোগ্রামিং জিরো টু হিরো",
        "c-programming-zero-to-hero",
        "শূন্য থেকে শুরু করে বোর্ড ও ভার্সিটি লেভেল প্রোগ্রামিং",
        "৩ মাস",
        True,
        True,
        ["সি এর বেসিক", "কন্ট্রোল স্টেটমেন্ট", "অ্যারে ও ফাংশন"],
    ),
    (
        "এইচটিএমএল ও ওয়েব ডিজাইন মাস্টারক্লাস",
        "html-web-design-masterclass",
        "হাতে-কলমে ওয়েবসাইট তৈরি করে চতুর্থ অধ্যায় শেষ",
        "৮ সপ্তাহ",
        True,
        True,
        ["এইচটিএমএল ট্যাগ পরিচিতি", "টেবিল, ফর্ম ও লিস্ট", "সিএসএস দিয়ে ডিজাইন"],
    ),
    (
        "এসএসসি আইসিটি সম্পূর্ণ প্রস্তুতি",
        "ssc-ict-full-preparation",
        "এসএসসি সিলেবাস অনুযায়ী অধ্যায়ভিত্তিক ক্লাস ও পরীক্ষা",
        "৪ মাস",
        True,
        True,
        ["তথ্য ও যোগাযোগ প্রযুক্তি", "কম্পিউটার ও যন্ত্রাংশ", "ইন্টারনেট ও ই-মেইল"],
    ),
    (
        "ভার্সিটি ভর্তি আইসিটি ফাইনাল রিভিশন",
        "admission-ict-final-revision",
        "ঢাবি, রাবি ও গুচ্ছ ভর্তি পরীক্ষার প্রশ্নব্যাংক সমাধান",
        "১০ সপ্তাহ",
        False,
        True,
        ["গুরুত্বপূর্ণ সূত্র রিভিশন", "প্রশ্নব্যাংক সমাধান", "ফাইনাল মডেল টেস্ট"],
    ),
]

#: (title, description, icon) -- the landing page's highlight cards.
COURSE_HIGHLIGHTS = [
    ("এককালীন পেমেন্ট", "একবার পেমেন্টে কোর্সের মেয়াদ পর্যন্ত পূর্ণ এক্সেস।", "wallet"),
    ("লাইভ ক্লাস ও রেকর্ডিং", "প্রতিটি অধ্যায়ে লাইভ ক্লাস, পরে রেকর্ডিং দেখার সুযোগ।", "video"),
    ("এমসিকিউ পরীক্ষা ও র‍্যাঙ্কিং", "অধ্যায়ভিত্তিক পরীক্ষা দিয়ে নিজের অবস্থান যাচাই।", "trophy"),
    ("লেকচার শিট ও হ্যান্ডনোট", "প্রতিটি ক্লাসের পিডিএফ লেকচার শিট।", "file-text"),
    ("২৪/৭ সাপোর্ট গ্রুপ", "যেকোনো প্রশ্নের উত্তর পেতে সাপোর্ট গ্রুপ।", "message-circle"),
]

COURSE_OUTCOMES = [
    ("পুরো সিলেবাস অধ্যায়ভিত্তিকভাবে শেষ করা", "book-open"),
    ("বোর্ড প্রশ্নের ধরন বুঝে উত্তর লেখা", "pen-tool"),
    ("এমসিকিউ-তে দ্রুত ও নির্ভুল উত্তর দেওয়া", "target"),
]

COURSE_AUDIENCE = ["এই বছরের পরীক্ষার্থী", "যারা অধ্যায়ভিত্তিক রিভিশন চায়"]

COURSE_REQUIREMENTS = ["স্মার্টফোন বা কম্পিউটার", "ইন্টারনেট সংযোগ"]

COURSE_FAQS = [
    ("ক্লাস মিস করলে কী হবে?", "প্রতিটি লাইভ ক্লাসের রেকর্ডিং কোর্সে যুক্ত করা হয়।"),
    ("কোর্সের মেয়াদ কতদিন?", "কোর্স পেজে দেওয়া প্রাইস অনুযায়ী মেয়াদ নির্ধারিত হয়।"),
]

#: name, slug -- the education levels, in academic order
CLASS_LEVELS = [
    ("এসএসসি", "ssc"),
    ("এইচএসসি", "hsc"),
]

#: name, slug
ACADEMIC_GROUPS = [
    ("বিজ্ঞান", "science"),
    ("মানবিক", "arts"),
    ("ব্যবসায় শিক্ষা", "commerce"),
    ("সাধারণ", "general"),
]

#: A subject is one row per education level and group.
#: name, slug stem, class level slug, group slug
SUBJECTS = [
    ("আইসিটি", "ict", "ssc", "science"),
    ("আইসিটি", "ict", "hsc", "science"),
    ("আইসিটি", "ict", "hsc", "commerce"),
    ("প্রোগ্রামিং", "programming", "hsc", "science"),
    ("ওয়েব ডিজাইন", "web-design", "hsc", "science"),
]

#: Chapters per subject, and the topics inside each. The names are Bengali,
#: so their slugs are just the parent's slug plus a number.
#: title, price (BDT)
PRODUCTS = [
    ("HSC ICT ফুল প্যাকেজ", 4500),
    ("লাইভ + রেকর্ডেড কম্বো", 3000),
    ("প্রোগ্রামিং বান্ডেল", 2500),
]

CHAPTERS = [
    ("সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস", ["বাইনারি সংখ্যা", "লজিক গেট"]),
    ("কমিউনিকেশন সিস্টেমস ও নেটওয়ার্কিং", ["ট্রান্সমিশন মিডিয়া", "নেটওয়ার্ক টপোলজি"]),
    ("ডেটাবেজ ম্যানেজমেন্ট সিস্টেম", ["এসকিউএল", "নরমালাইজেশন"]),
]

#: One batch per level per year, named `<label>-<year>`.
BATCH_LABELS = {
    "ssc": "SSC",
    "hsc": "HSC",
}
BATCH_YEARS = (2027, 2028)

#: name, designation, employment type, bio, subjects taught
TEACHERS = [
    (
        "রাহাদ স্যার",
        "প্রতিষ্ঠাতা ও প্রধান পরিচালক",
        "permanent",
        "১২ বছরের বেশি সময় ধরে এইচএসসি আইসিটি পড়াচ্ছেন। ৫০,০০০+ শিক্ষার্থীর প্রিয় শিক্ষক।",
        ["আইসিটি"],
    ),
    (
        "তানভীর হাসান",
        "সিনিয়র ইন্সট্রাক্টর, প্রোগ্রামিং",
        "permanent",
        "বুয়েট সিএসই থেকে স্নাতক। সি ও পাইথন প্রোগ্রামিং এর ক্লাস নেন।",
        ["প্রোগ্রামিং"],
    ),
    (
        "নুসরাত জাহান",
        "ইন্সট্রাক্টর, ওয়েব ডিজাইন",
        "guest",
        "ফ্রন্টএন্ড ডেভেলপার ও শিক্ষক। এইচটিএমএল, সিএসএস ও ওয়েব ডিজাইন অধ্যায় পড়ান।",
        ["ওয়েব ডিজাইন"],
    ),
    (
        "সাইফুল ইসলাম",
        "ইন্সট্রাক্টর, ডেটাবেজ",
        "guest",
        "ঢাকা বিশ্ববিদ্যালয়ের আইআইটি থেকে স্নাতকোত্তর। ডেটাবেজ ও নেটওয়ার্কিং পড়ান।",
        ["আইসিটি"],
    ),
]

TESTIMONIALS = [
    (
        "সাদিয়া আফরিন",
        "এইচএসসি ২০২৫, ভিকারুননিসা নূন কলেজ",
        5,
        "আইসিটি সবচেয়ে ভয়ের সাবজেক্ট ছিল। রাহাদ স্যারের ক্লাস করে বোর্ডে এ প্লাস পেয়েছি।",
    ),
    ("মেহেদী হাসান", "এইচএসসি ২০২৫, নটর ডেম কলেজ", 5, "সংখ্যা পদ্ধতির অংক এত সহজে বুঝিয়ে দেওয়ার কারণে পরীক্ষায় একটাও ভুল হয়নি।"),
    ("ফারহানা ইয়াসমিন", "এইচএসসি ২০২৪, রাজশাহী কলেজ", 4, "লাইভ ক্লাসের রেকর্ডিং যেকোনো সময় দেখা যায়, এটাই সবচেয়ে বড় সুবিধা।"),
    ("আরিফুল ইসলাম", "ভর্তি পরীক্ষার্থী, ঢাকা", 5, "প্রশ্নব্যাংক সমাধানের ক্লাসগুলো ভর্তি পরীক্ষায় অনেক কাজে দিয়েছে।"),
    ("তাসনিম রহমান", "এসএসসি ২০২৫, ঢাকা", 5, "প্রতিটি অধ্যায় শেষে পরীক্ষা হওয়ায় নিজের দুর্বলতা ধরতে পেরেছি।"),
    ("রাকিবুল হাসান", "এইচএসসি ২০২৬, চট্টগ্রাম কলেজ", 4, "পিডিএফ শিটগুলো খুব গোছানো, আলাদা করে নোট করার দরকার হয় না।"),
]

NOTICE_CATEGORIES = [
    ("পরীক্ষা", "exam"),
    ("ক্লাস রুটিন", "class-routine"),
    ("ভর্তি বিজ্ঞপ্তি", "admission-notice"),
    ("সাধারণ", "general"),
]

NOTICES = [
    (
        "এইচএসসি ২০২৬ ব্যাচের ভর্তি চলছে",
        "hsc-2026-admission-open",
        "পরীক্ষা",
        "এইচএসসি ২০২৬ ব্যাচের আইসিটি ফুল কোর্সে ভর্তি চলছে। আসন সংখ্যা সীমিত, আগে আসলে আগে পাবেন ভিত্তিতে ভর্তি নেওয়া হচ্ছে।",
    ),
    (
        "তৃতীয় অধ্যায়ের মডেল টেস্টের সময়সূচি",
        "model-test-schedule-chapter-3",
        "পরীক্ষা",
        "আগামী শুক্রবার রাত ৯টায় সংখ্যা পদ্ধতি ও ডিজিটাল ডিভাইস অধ্যায়ের মডেল টেস্ট অনুষ্ঠিত হবে। মোট ৩০টি এমসিকিউ, সময় ২০ মিনিট।",
    ),
    (
        "নতুন ক্লাস রুটিন প্রকাশিত",
        "new-class-routine-published",
        "ক্লাস রুটিন",
        "চলতি মাসের নতুন ক্লাস রুটিন প্রকাশ করা হয়েছে। প্রতি রবি, মঙ্গল ও বৃহস্পতিবার রাত ৮টায় লাইভ ক্লাস হবে।",
    ),
    (
        "ঈদের ছুটিতে ক্লাস বন্ধ থাকবে",
        "eid-holiday-class-closed",
        "সাধারণ",
        "ঈদুল আজহা উপলক্ষে পাঁচ দিন লাইভ ক্লাস বন্ধ থাকবে। তবে রেকর্ডেড ক্লাস ও পরীক্ষা যথারীতি চালু থাকবে।",
    ),
    (
        "ভার্সিটি ভর্তি ব্যাচের ফ্রি সেমিনার",
        "free-admission-seminar",
        "ভর্তি বিজ্ঞপ্তি",
        "ভর্তি পরীক্ষায় আইসিটি থেকে সর্বোচ্চ নম্বর তোলার কৌশল নিয়ে ফ্রি সেমিনার। রেজিস্ট্রেশন করে অংশ নিন।",
    ),
    (
        "লেকচার শিট ডাউনলোড চালু হয়েছে",
        "lecture-sheet-download-live",
        "সাধারণ",
        "সকল ভর্তিকৃত শিক্ষার্থী এখন কোর্সের ভেতর থেকে অধ্যায়ভিত্তিক পিডিএফ লেকচার শিট ডাউনলোড করতে পারবেন।",
    ),
]

EBOOKS = [
    ("আইসিটি সূত্র সমগ্র", "এক নজরে ছয় অধ্যায়ের সব সূত্র ও শর্টকাট টেকনিক।"),
    ("বোর্ড প্রশ্নব্যাংক ২০১৭-২০২৫", "সকল বোর্ডের এমসিকিউ ও সৃজনশীল প্রশ্নের সমাধানসহ সংকলন।"),
    ("সি প্রোগ্রামিং হ্যান্ডনোট", "সিনট্যাক্স, লুপ ও ফাংশনের সহজ ব্যাখ্যা ও উদাহরণ।"),
]

STUDENT_NAMES = [
    "সাদিয়া আফরিন",
    "মেহেদী হাসান",
    "ফারহানা ইয়াসমিন",
    "আরিফুল ইসলাম",
    "তাসনিম রহমান",
    "রাকিবুল হাসান",
    "নুসরাত জাহান",
    "সাইফুল ইসলাম",
    "জান্নাতুল ফেরদৌস",
    "শাহরিয়ার কবির",
    "মাহমুদা খাতুন",
    "ইমরান হোসেন",
    "সুমাইয়া আক্তার",
    "তানভীর আহমেদ",
    "রুবাইয়া ইসলাম",
    "নাফিস ইকবাল",
    "লামিয়া চৌধুরী",
    "আসিফ মাহমুদ",
    "সানজিদা পারভীন",
    "হাসিবুল হক",
    "মারিয়া তাবাসসুম",
    "রায়হান কবির",
    "অন্তরা দাস",
    "সৌরভ মজুমদার",
    "ইশরাত জাহান",
]

INSTITUTIONS = [
    "ঢাকা কলেজ",
    "নটর ডেম কলেজ",
    "ভিকারুননিসা নূন কলেজ",
    "রাজশাহী কলেজ",
    "চট্টগ্রাম কলেজ",
    "আদমজী ক্যান্টনমেন্ট কলেজ",
    "সরকারি বিজ্ঞান কলেজ",
]

ADDRESSES = [
    "১২/ক, ধানমন্ডি, ঢাকা",
    "৪৫ গ্রীন রোড, ফার্মগেট, ঢাকা",
    "৭ নং সেক্টর, উত্তরা, ঢাকা",
    "২৩ মিরপুর রোড, ঢাকা",
    "৯ কাজী নজরুল ইসলাম এভিনিউ, ঢাকা",
]

# (question, a, b, c, d, answer, explanation)
STATIC_PAGES = [
    # The client requests this key literally (see the web app's about page).
    (
        "about",
        "html",
        "<h2>আমাদের সম্পর্কে</h2><p>শমাধান কোচিং দেশের যেকোনো প্রান্তের শিক্ষার্থীর কাছে "
        "মানসম্মত আইসিটি শিক্ষা পৌঁছে দেওয়ার লক্ষ্যে কাজ করছে। ২০১৮ সাল থেকে এখন পর্যন্ত "
        "৫০ হাজারের বেশি শিক্ষার্থী আমাদের কোর্সে যুক্ত হয়েছেন।</p>",
    ),
    (
        "our-goal",
        "html",
        "<h2>আমাদের লক্ষ্য</h2><p>প্রতিটি শিক্ষার্থী যেন আইসিটি বিষয়ে আত্মবিশ্বাসের সাথে "
        "পরীক্ষা দিতে পারে এবং বাস্তব জীবনে প্রযুক্তি ব্যবহার করতে শেখে — এটাই আমাদের লক্ষ্য।</p>",
    ),
    (
        "terms-and-conditions",
        "html",
        "<h2>শর্তাবলি</h2><p>কোর্সে ভর্তির পর ফি ফেরতযোগ্য নয়। একটি অ্যাকাউন্ট শুধু একজন "
        "শিক্ষার্থী ব্যবহার করতে পারবেন। ক্লাসের ভিডিও রেকর্ড বা বিতরণ করা সম্পূর্ণ নিষিদ্ধ।</p>",
    ),
    (
        "privacy-policy",
        "html",
        "<h2>গোপনীয়তা নীতি</h2><p>আমরা শিক্ষার্থীর নাম, মোবাইল নম্বর ও প্রতিষ্ঠানের তথ্য "
        "শুধুমাত্র কোর্স পরিচালনার জন্য সংগ্রহ করি এবং তৃতীয় পক্ষের সাথে শেয়ার করি না।</p>",
    ),
    (
        "refund-policy",
        "html",
        "<h2>রিফান্ড নীতি</h2><p>ভুল পেমেন্টের ক্ষেত্রে ৭ কার্যদিবসের মধ্যে আবেদন করলে যাচাই সাপেক্ষে অর্থ ফেরত দেওয়া হয়।</p>",
    ),
    (
        "contact-info",
        "html",
        "<h2>যোগাযোগ</h2><p>মোবাইল: ০১৭১১৭৭৮৬০২<br/>ইমেইল: support@shomadhan.local<br/>ঠিকানা: ১২/এ, গ্রীন রোড, ঢাকা ১২০৫</p>",
    ),
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
        # manage.py falls back to the local settings, where DEBUG is always on, so DEBUG alone proves nothing.
        disposable = connection.vendor == "sqlite" or os.environ.get("ALLOW_DEMO_SEED") == "1"
        if not (settings.DEBUG and disposable):
            raise CommandError(
                "seed_demo writes fake data and --fresh empties tables. It runs only with DEBUG on and a SQLite "
                "database; set ALLOW_DEMO_SEED=1 to seed a disposable Postgres."
            )
        self.rng = random.Random(RNG_SEED)
        self.now = timezone.now()

        if options["fresh"]:
            self._wipe()

        self._seed_pages()
        self._seed_academic()
        teachers = self._seed_teachers()
        self._seed_testimonials()
        self._seed_advertisements()
        self._seed_notices()
        self._seed_ebooks()
        courses = self._seed_courses(teachers)
        students = self._seed_students()
        self._seed_enrollments(courses, students)
        products = self._seed_products(courses)
        self._seed_orders(courses, products, students)
        self._seed_materials(courses)

        self.stdout.write(self.style.SUCCESS("\nDemo data ready:"))
        for label, count in [
            ("courses", Course.objects.count()),
            ("sections", Section.objects.count()),
            ("contents", Content.objects.count()),
            ("class levels", ClassLevel.objects.count()),
            ("academic groups", Group.objects.count()),
            ("subjects", Subject.objects.count()),
            ("chapters", Chapter.objects.count()),
            ("topics", Topic.objects.count()),
            ("batches", Batch.objects.count()),
            ("teachers", TeacherProfile.objects.count()),
            ("testimonials", Testimonial.objects.count()),
            ("notices", Notice.objects.count()),
            ("students", User.objects.filter(groups__name=User.Role.STUDENT).count()),
            ("enrollments", Enrollment.objects.count()),
            ("products", Product.objects.count()),
            ("payments", Payment.objects.count()),
        ]:
            self.stdout.write(f"  {count:>5}  {label}")
        self.stdout.write("\nStudent logins: phone 01810000001 … 01810000025, password student1234")

    # -- wipe ---------------------------------------------------------------

    def _wipe(self):
        self.stdout.write("Removing existing demo rows...")
        for model in [
            Payment,
            Product,
            Enrollment,
            Content,
            Section,
            Routine,
            CourseTeacher,
            Course,
            CourseMaterial,
            Notice,
            NoticeCategory,
            EBook,
            Advertisement,
            Testimonial,
            TeacherProfile,
            Batch,
            Topic,
            Chapter,
            Subject,
            ClassLevel,
            Group,
        ]:
            model.objects.all().delete()
        # Only the exact accounts this command mints: their prefixes are real operators' ranges.
        User.objects.filter(phone__in=[student_phone(i) for i in range(len(STUDENT_NAMES))]).delete()
        User.objects.filter(phone__in=[teacher_phone(i) for i in range(len(TEACHERS))]).delete()
        Page.objects.exclude(
            key__in=["homeBannerImage", "homeCourseCounter", "homeStudentCounter", "homeInstructorCounter"]
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
                key=key, defaults={"slug": key, "value_type": Page.ValueType.COUNTER, "value": value}
            )
        Page.objects.update_or_create(
            key="homeBannerImage",
            defaults={"slug": "homeBannerImage", "value_type": Page.ValueType.IMAGE, "value": "", "image": banner},
        )
        for index, (key, value_type, value) in enumerate(STATIC_PAGES):
            Page.objects.update_or_create(
                key=key,
                defaults={
                    "slug": key,
                    "value_type": value_type,
                    "value": value,
                    "image": make_image(f"page-{key}", 1200, 630, key.upper()[:12], index + 1),
                },
            )
        self.stdout.write("  pages + homepage counters")

    def _seed_academic(self):
        """Education levels, groups, subjects and batches.

        Slugs are passed rather than generated: the names are Bangla and
        slugs are English ("ssc", "science").
        """
        levels = {}
        for order, (name, slug) in enumerate(CLASS_LEVELS):
            levels[slug], _ = ClassLevel.objects.get_or_create(name=name, defaults={"slug": slug, "order": order})

        groups = {}
        for order, (name, slug) in enumerate(ACADEMIC_GROUPS):
            groups[slug], _ = Group.objects.get_or_create(name=name, defaults={"slug": slug, "order": order})

        for order, (name, stem, level_slug, group_slug) in enumerate(SUBJECTS):
            Subject.objects.get_or_create(
                name=name,
                class_level=levels[level_slug],
                group=groups[group_slug],
                defaults={"slug": f"{stem}-{level_slug}-{group_slug}", "order": order},
            )

        for subject in Subject.objects.all():
            for number, (chapter_name, topics) in enumerate(CHAPTERS, start=1):
                chapter, _ = Chapter.objects.get_or_create(
                    name=chapter_name, subject=subject, defaults={"chapter_number": number}
                )
                for topic_name in topics:
                    Topic.objects.get_or_create(name=topic_name, chapter=chapter)

        order = 0
        for level_slug, label in BATCH_LABELS.items():
            for year in BATCH_YEARS:
                Batch.objects.get_or_create(
                    name=f"{label}-{year}",
                    class_level=levels[level_slug],
                    defaults={"order": order},
                )
                order += 1

        self.stdout.write("  academic levels, groups, subjects, chapters, topics and batches")

    def _seed_teachers(self):
        """A teacher is an account with a profile, not a roster row.

        Active, but with no password, so none of them can sign in until an
        admin gives them one. `is_active=False` is what `deactivate_user` sets,
        so using it here would make a teacher look like a blocked account.
        """
        levels = list(ClassLevel.objects.all())
        teachers = []
        for index, (name, designation, kind, description, subjects) in enumerate(TEACHERS):
            phone = teacher_phone(index)
            user = User.objects.filter(phone=phone).first()
            if user is None:
                # `create_user` marks the password unusable; writing the row
                # directly leaves the field's empty-string default, which
                # Django reports as usable.
                user = User.objects.create_user(
                    phone=phone,
                    password=None,
                    name=name,
                    email=f"teacher{index + 1}@shomadhan.local",
                    image=make_image(f"teacher-{index}", 500, 500, f"T{index + 1}", index + 3),
                )
            user.set_role(User.Role.TEACHER)
            profile, _ = TeacherProfile.objects.get_or_create(
                user=user,
                defaults={
                    "designation": designation,
                    "type": kind,
                    "description": description,
                    "order": index,
                    "institute": "শমাধান কোচিং",
                },
            )
            profile.subjects.set(Subject.objects.filter(name__in=subjects))
            profile.levels.set(levels)
            teachers.append(user)
        self.stdout.write("  teachers")
        return teachers

    def _seed_testimonials(self):
        for index, (name, designation, rating, text) in enumerate(TESTIMONIALS):
            Testimonial.objects.get_or_create(
                name=name,
                defaults={
                    "designation": designation,
                    "ratings": rating,
                    "description": text,
                    "image": make_image(f"student-{index}", 400, 400, f"S{index + 1}", index),
                },
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
                defaults={
                    "description": description,
                    "type": kind,
                    "link": "http://localhost:3000/course",
                    "image": make_image(f"ad-{index}", 1200, 400, f"AD {index + 1}", index + 1),
                },
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
                defaults={
                    "title": title,
                    "body": body,
                    "image": make_image(f"notice-{index}", 900, 500, f"NOTICE {index + 1}", index + 2),
                },
            )
            if created:
                notice.categories.add(categories[category_title])
                # Spread notices back through the last few weeks so the list
                # is not a single timestamp.
                Notice.objects.filter(pk=notice.pk).update(created_at=self.now - timedelta(days=index * 5 + 1))
        self.stdout.write("  notices")

    def _seed_ebooks(self):
        for index, (title, description) in enumerate(EBOOKS):
            EBook.objects.get_or_create(
                title=title,
                defaults={
                    "description": description,
                    "booking_link": "http://localhost:3000/contact",
                    "preview": f"{MEDIA_BASE}/{SEED_DIR}/ebook-{index}.png",
                    "image": make_image(f"ebook-{index}", 600, 800, f"EBOOK {index + 1}", index + 4),
                },
            )
        self.stdout.write("  ebooks")

    # -- exams --------------------------------------------------------------

    def _seed_courses(self, teachers):
        courses = []
        for index, row in enumerate(COURSES):
            title, slug, subtitle, duration, featured, is_online, chapters = row
            course, created = Course.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "subtitle": subtitle,
                    "duration": duration,
                    "summary": subtitle,
                    "is_featured": featured,
                    "is_online": is_online,
                    "delivery": Course.Delivery.HYBRID if is_online else Course.Delivery.LIVE,
                    "difficulty": Course.Difficulty.INTERMEDIATE,
                    "status": Course.Status.PUBLISHED,
                    "fake_student_count": self.rng.randint(400, 4200),
                    "description": (
                        f"<p>{subtitle}</p><p>কোর্সটিতে মোট {len(chapters)}টি অধ্যায় রয়েছে। "
                        "প্রতিটি অধ্যায়ে থাকছে রেকর্ডেড ভিডিও ক্লাস, লেকচার শিট, "
                        "অধ্যায়ভিত্তিক এমসিকিউ পরীক্ষা এবং লাইভ প্রশ্নোত্তর সেশন।</p>"
                    ),
                    "highlights": [{"title": t, "description": d, "icon": i} for t, d, i in COURSE_HIGHLIGHTS],
                    "learning_outcomes": [{"title": t, "icon": i} for t, i in COURSE_OUTCOMES],
                    "target_audience": [{"title": t} for t in COURSE_AUDIENCE],
                    "requirements": [{"title": t} for t in COURSE_REQUIREMENTS],
                    "faqs": [{"question": q, "answer": a} for q, a in COURSE_FAQS],
                    "promo_video": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    "thumbnail": make_image(f"course-{index}", 800, 450, f"COURSE {index + 1}", index),
                    "banner": make_image(f"course-{index}-banner", 1600, 500, f"COURSE {index + 1}", index),
                },
            )
            if created:
                self._seed_course_packages(course, index)
                self._seed_course_extras(course, teachers, index)
                self._seed_course_tree(course, chapters, index, slug)
            courses.append(course)
        self.stdout.write("  courses + sections + contents")
        return courses

    def _seed_course_packages(self, course, index):
        """Two packages per course, as billing sells it: a year with a
        struck-through "was" price on every other course, and a month."""
        base = 1500 + index * 500
        full = Product.objects.create(
            title=f"{course.title} — ১ বছর",
            description="পুরো কোর্সে এক বছরের এক্সেস।",
            price=base - 300 if index % 2 == 0 else base,
            base_price=base,
            access_days=365,
        )
        monthly = Product.objects.create(
            title=f"{course.title} — ১ মাস",
            description="৩০ দিনের এক্সেস।",
            price=base // 5,
            base_price=base // 5,
            access_days=30,
        )
        full.courses.add(course)
        monthly.courses.add(course)

    def _seed_course_extras(self, course, teachers, index):
        # The assignment names the account and the commission. Everything the
        # course page shows about the person is read through their profile.
        CourseTeacher.objects.get_or_create(
            course=course,
            user=teachers[index % len(teachers)],
            defaults={"commission": Decimal("25.00"), "order": 0},
        )
        for label in ["সাপ্তাহিক ক্লাস রুটিন", "পরীক্ষার সময়সূচি"]:
            Routine.objects.create(
                course=course,
                title=label,
                link=f"{MEDIA_BASE}/{SEED_DIR}/course-{index}.png",
            )

    def _seed_course_tree(self, course, chapters, course_index, course_slug):
        """One section per chapter: video lessons, a lecture sheet, a note, a
        live class and a chapter exam wired to an MCQ folder."""
        for chapter_index, chapter in enumerate(chapters):
            chapter_slug = f"{course_slug}-ch{chapter_index + 1}"
            section = Section.objects.create(
                course=course,
                title=chapter,
                slug=chapter_slug,
                order=chapter_index,
                active=True,
            )
            order = 0

            for lesson_index in range(3):
                Content.objects.create(
                    course=course,
                    section=section,
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
                course=course,
                section=section,
                title=f"{chapter} — লেকচার শিট",
                slug=f"{chapter_slug}-sheet",
                type=Content.Type.PDF,
                paid=True,
                order=order,
                pdf_file=f"{MEDIA_BASE}/{SEED_DIR}/course-{course_index}.png",
            )
            order += 1

            Content.objects.create(
                course=course,
                section=section,
                title=f"{chapter} — হ্যান্ডনোট",
                slug=f"{chapter_slug}-note",
                type=Content.Type.NOTE,
                paid=True,
                order=order,
                note_body=(
                    f"<h3>{chapter}</h3><ul>"
                    "<li>অধ্যায়ের গুরুত্বপূর্ণ সংজ্ঞা ও সূত্র</li>"
                    "<li>বোর্ড পরীক্ষায় বারবার আসা প্রশ্নের তালিকা</li>"
                    "<li>সাধারণ ভুল ও তা এড়ানোর কৌশল</li></ul>"
                ),
            )
            order += 1

            Content.objects.create(
                course=course,
                section=section,
                title=f"{chapter} — লাইভ প্রশ্নোত্তর",
                slug=f"{chapter_slug}-live",
                type=Content.Type.LIVE,
                paid=True,
                order=order,
                live_url="https://meet.google.com/demo-shomadhan",
                live_scheduled_at=self.now + timedelta(days=chapter_index * 3 + 2),
            )
            order += 1

            Content.objects.create(
                course=course,
                section=section,
                title=f"{chapter} — অধ্যায়ভিত্তিক পরীক্ষা",
                slug=f"{chapter_slug}-exam",
                type=Content.Type.EXAM,
                paid=True,
                order=order,
            )

    def _seed_materials(self, courses):
        for index, course in enumerate(courses[:4]):
            CourseMaterial.objects.get_or_create(
                title=f"{course.title} — সাপ্লিমেন্টারি শিট",
                defaults={"type": "pdf", "course": course, "file": f"{MEDIA_BASE}/{SEED_DIR}/course-{index}.png"},
            )
        self.stdout.write("  course materials")

    # -- students -----------------------------------------------------------

    def _seed_students(self):
        class_levels = list(ClassLevel.objects.all())
        groups = list(Group.objects.all())
        students = []
        for index, name in enumerate(STUDENT_NAMES):
            phone = student_phone(index)
            student = User.objects.filter(phone=phone).first()
            if student is None:
                joined = self.now - timedelta(days=self.rng.randint(3, 330))
                student = User.objects.create_user(
                    phone=phone,
                    email=f"student{index + 1}@shomadhan.local",
                    password="student1234",
                    name=name,
                    role=User.Role.STUDENT,
                    phone_verified_at=joined,
                    date_joined=joined,
                    image=make_image(f"avatar-{index}", 300, 300, f"U{index + 1}", index),
                )
                profile = StudentProfile.objects.create(
                    user=student,
                    institution=INSTITUTIONS[index % len(INSTITUTIONS)],
                    educational_session=self.rng.choice(["২০২৪-২৫", "২০২৫-২৬", "২০২৬-২৭"]),
                    address=self.rng.choice(ADDRESSES),
                    class_level=self.rng.choice(class_levels) if class_levels else None,
                    group=self.rng.choice(groups) if groups else None,
                )
                GuardianProfile.objects.create(
                    student=profile,
                    name=f"{name.split()[-1]} সাহেব",
                    phone=f"0191000{index + 1:04d}",
                    relation="অভিভাবক",
                )
            students.append(student)
        self.stdout.write("  students")
        return students

    def _seed_enrollments(self, courses, students):
        for student in students:
            for course in self.rng.sample(courses, self.rng.randint(1, 3)):
                Enrollment.objects.get_or_create(
                    course=course,
                    user=student,
                    defaults={
                        "payment_type": Enrollment.PaymentType.PAID,
                        "valid_till": self.now + timedelta(days=365),
                    },
                )
        self.stdout.write("  enrollments")

    def _seed_products(self, courses):
        """A few bundles, each unlocking two courses for a year."""
        products = []
        for index, (title, amount) in enumerate(PRODUCTS):
            product, created = Product.objects.get_or_create(
                title=title,
                defaults={
                    "description": f"{title} — access to the courses below for one year.",
                    "price": amount,
                    "base_price": amount,
                    "access_days": 365,
                },
            )
            if created:
                product.courses.set(courses[index : index + 2])
            products.append(product)
        self.stdout.write("  products")
        return products

    def _seed_orders(self, courses, products, students):
        """Payments back-dated across the last 12 months. `created_at` is
        auto_now_add, so it is rewritten with a queryset update."""
        if Payment.objects.exists():
            self.stdout.write("  payments (already present, skipped)")
            return

        card_types = ["BKASH-BKash", "NAGAD-Nagad", "VISA-Dutch Bangla", "MASTER-City Bank"]
        bought = set()
        for _ in range(90):
            student = self.rng.choice(students)
            product = self.rng.choice(products)
            days_ago = self.rng.randint(0, 360)
            created = self.now - timedelta(days=days_ago, hours=self.rng.randint(0, 23))

            status = self.rng.choices(
                [Payment.Status.VALID, Payment.Status.INITIATED, Payment.Status.CANCELLED],
                weights=[78, 15, 7],
            )[0]
            # A product is bought once; a second attempt is left unfinished.
            if status == Payment.Status.VALID and (student.pk, product.pk) in bought:
                status = Payment.Status.CANCELLED
            settled = status == Payment.Status.VALID
            if settled:
                bought.add((student.pk, product.pk))
            payment = Payment.objects.create(
                user=student,
                product=product,
                amount=product.price,
                access_until=created + timedelta(days=product.access_days),
                status=status,
                card_type=self.rng.choice(card_types) if settled else "",
                transaction_date=created if settled else None,
            )
            Payment.objects.filter(pk=payment.pk).update(created_at=created)
        self.stdout.write("  payments")
