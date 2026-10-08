from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.academic.models import Batch, ClassLevel
from apps.communication.models import Notice, NoticeCategory
from apps.courses.models import Course

PREFIX = "demo-notice-"
BATCH_SLUG = "demo-hsc-2027"
BATCH_COURSE = "demo-hsc-physics-live-2027"

CATEGORIES = [
    ("ভর্তি", "admission"),
    ("পরীক্ষা", "exam"),
    ("ক্লাস রুটিন", "routine"),
    ("ছুটি", "holiday"),
    ("ফলাফল", "result"),
]

#: (slug, category slug, days ago, class level slugs, for the demo batch, title, body)
NOTICES = [
    (
        "eid-holiday",
        "holiday",
        0,
        [],
        False,
        "ঈদুল আজহা উপলক্ষে ক্লাস বন্ধ",
        "<p>ঈদুল আজহা উপলক্ষে <strong>১২ থেকে ১৮ অক্টোবর</strong> পর্যন্ত সব অনলাইন ও অফলাইন ক্লাস বন্ধ থাকবে। "
        "১৯ অক্টোবর থেকে আগের রুটিন অনুযায়ী ক্লাস চলবে।</p><p>সবাইকে ঈদের শুভেচ্ছা।</p>",
    ),
    (
        "hsc-model-test",
        "exam",
        0,
        ["hsc"],
        False,
        "এইচএসসি আইসিটি মডেল টেস্ট — শুক্রবার সকাল ১০টা",
        "<p>এইচএসসি পরীক্ষার্থীদের জন্য পূর্ণাঙ্গ মডেল টেস্ট অনুষ্ঠিত হবে।</p>"
        "<ul><li>তারিখ: শুক্রবার</li><li>সময়: সকাল ১০টা – দুপুর ১২:৩০</li>"
        "<li>সিলেবাস: অধ্যায় ১–৬</li></ul><p>পরীক্ষা ওয়েবসাইটের ‘আমার কোর্স’ থেকে দেওয়া যাবে।</p>",
    ),
    (
        "batch-extra-class",
        "routine",
        1,
        [],
        True,
        "এইচএসসি ২০২৭ ব্যাচ: শনিবার এক্সট্রা ক্লাস",
        "<p>প্রোগ্রামিং অধ্যায়ের বাকি অংশ শেষ করতে শনিবার সন্ধ্যা ৭টায় একটি এক্সট্রা লাইভ ক্লাস হবে। লিংক ক্লাসের আগে দেওয়া হবে।</p>",
    ),
    (
        "ssc-routine",
        "routine",
        2,
        ["ssc"],
        False,
        "এসএসসি ব্যাচের নতুন ক্লাস রুটিন",
        "<p>নভেম্বর মাস থেকে এসএসসি ব্যাচের ক্লাস সপ্তাহে তিন দিন হবে: <strong>রবি, মঙ্গল ও বৃহস্পতিবার</strong>, "
        "বিকেল ৪টা থেকে ৫:৩০।</p>",
    ),
    (
        "admission-2027",
        "admission",
        3,
        [],
        False,
        "এইচএসসি ২০২৭ ব্যাচে ভর্তি চলছে",
        "<p>এইচএসসি ২০২৭ আইসিটি লাইভ ব্যাচে ভর্তি চলছে। প্রথম ১০০ জনের জন্য বিশেষ ছাড়।</p>"
        "<p>বিস্তারিত জানতে ‘সকল কোর্স’ পাতায় দেখুন বা আমাদের হোয়াটসঅ্যাপে যোগাযোগ করুন।</p>",
    ),
    (
        "monthly-result",
        "result",
        6,
        ["hsc", "ssc"],
        False,
        "সেপ্টেম্বর মাসিক পরীক্ষার ফলাফল প্রকাশ",
        "<p>সেপ্টেম্বর মাসিক পরীক্ষার ফলাফল প্রকাশিত হয়েছে। নিজের ফলাফল ‘আমার কোর্স’ → পরীক্ষা অংশে দেখা যাবে।</p>",
    ),
    (
        "ssc-suggestion",
        "exam",
        12,
        ["ssc"],
        False,
        "এসএসসি আইসিটি শর্ট সাজেশন প্রকাশিত",
        "<p>এসএসসি পরীক্ষার্থীদের জন্য শর্ট সাজেশন স্টাডি ম্যাটেরিয়াল পাতায় দেওয়া হয়েছে।</p>",
    ),
    (
        "website-launch",
        "admission",
        20,
        [],
        False,
        "নতুন ওয়েবসাইটে স্বাগতম",
        "<p>এখন থেকে কোর্স কেনা, ক্লাস দেখা, পরীক্ষা দেওয়া আর নোটিশ — সব এক জায়গায়। কোনো সমস্যা হলে আমাদের জানাও।</p>",
    ),
    (
        "independence-day",
        "holiday",
        45,
        [],
        False,
        "জাতীয় দিবস উপলক্ষে ক্লাস বন্ধ",
        "<p>জাতীয় দিবস উপলক্ষে সেদিন কোনো ক্লাস হবে না।</p>",
    ),
]


class Command(BaseCommand):
    help = "Replace the example notices (for everyone, by class, and for a demo batch); local testing only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Only remove the example notices and demo batch.")

    def handle(self, *args, clear=False, **options):
        Notice.objects.filter(slug__startswith=PREFIX).delete()
        NoticeCategory.objects.filter(slug__startswith=PREFIX).delete()
        Course.objects.filter(batch__slug=BATCH_SLUG).update(batch=None)
        Batch.objects.filter(slug=BATCH_SLUG).delete()
        if clear:
            self.stdout.write("Example notices removed.")
            return

        levels = {level.slug: level for level in ClassLevel.objects.all()}
        batch = Batch.objects.create(name="এইচএসসি ২০২৭", slug=BATCH_SLUG, class_level=levels["hsc"])
        Course.objects.filter(slug=BATCH_COURSE, batch__isnull=True).update(batch=batch)
        categories = {
            slug: NoticeCategory.objects.create(title=title, slug=f"{PREFIX}{slug}", order=order)
            for order, (title, slug) in enumerate(CATEGORIES)
        }

        now = timezone.now()
        for slug, category, days_ago, level_slugs, for_batch, title, body in NOTICES:
            notice = Notice.objects.create(title=title, slug=f"{PREFIX}{slug}", body=body)
            notice.categories.add(categories[category])
            notice.class_levels.set([levels[s] for s in level_slugs])
            if for_batch:
                notice.batches.add(batch)
            # Spread over the past weeks; one is older than the bell's 30-day window.
            Notice.objects.filter(pk=notice.pk).update(created_at=now - timezone.timedelta(days=days_ago, hours=1))

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(CATEGORIES)} categories, {len(NOTICES)} notices and the batch “{batch.name}” added."
            )
        )
