from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.academic.models import ClassLevel
from apps.courses.models import Course, Enrollment
from apps.feedback.models import Feedback
from apps.feedback.services import submit_feedback
from apps.identity.models import User
from apps.profiles.models import StudentProfile

PHONE_PREFIX = "0189990"

#: (name, class level slug, institution)
STUDENTS = [
    ("সাদিয়া আফরিন", "hsc", "সিলেট সরকারি মহিলা কলেজ"),
    ("মেহেদী হাসান", "hsc", "এমসি কলেজ"),
    ("ফারহানা ইয়াসমিন", "hsc", "সিলেট সরকারি কলেজ"),
    ("আরিফুল ইসলাম", "hsc", "শাহজালাল কলেজ"),
    ("তাসনিম রহমান", "ssc", "সিলেট সরকারি পাইলট হাই স্কুল"),
    ("রাকিবুল হাসান", "hsc", "এমসি কলেজ"),
    ("নুসরাত জাহান", "ssc", "ব্লু-বার্ড হাই স্কুল"),
    ("ইমরান হোসেন", "hsc", "সিলেট ক্যাডেট কলেজ"),
    ("জান্নাতুল ফেরদৌস", "ssc", "অগ্রগামী বালিকা উচ্চ বিদ্যালয়"),
    ("তানভীর আহমেদ", "hsc", "সিলেট সরকারি কলেজ"),
]

COURSE_COMMENTS = {
    5: [
        "প্রতিটি অধ্যায় খুব সহজ করে বোঝানো হয়েছে। বোর্ডের প্রশ্ন সমাধানের ক্লাসগুলো সবচেয়ে কাজের।",
        "রেকর্ডেড ক্লাস যেকোনো সময় দেখা যায়, আর লেকচার শিটগুলো খুব গোছানো।",
        "প্রোগ্রামিং অধ্যায়টা ভয় পেতাম, এখন নিজে নিজে কোড লিখতে পারি।",
        "অধ্যায় শেষে পরীক্ষা দেওয়ায় নিজের দুর্বলতা ধরতে পেরেছি।",
    ],
    4: [
        "কোর্সটা খুব ভালো, তবে আরও কিছু প্র্যাকটিস প্রশ্ন থাকলে ভালো হতো।",
        "লাইভ ক্লাসগুলো দারুণ, শুধু মাঝে মাঝে ভিডিও একটু দেরিতে আপলোড হয়।",
    ],
    3: ["কনটেন্ট ভালো, কিন্তু কয়েকটা লেসনের অডিও আরেকটু পরিষ্কার হলে ভালো হতো।"],
}

GENERAL_COMMENTS = [
    (5, "আইসিটি সবচেয়ে ভয়ের সাবজেক্ট ছিল। স্যারের ক্লাস করে বোর্ডে এ প্লাস পেয়েছি।", True),
    (5, "সংখ্যা পদ্ধতির অংক এত সহজে বুঝিয়ে দেওয়ার কারণে পরীক্ষায় একটাও ভুল হয়নি।", True),
    (4, "যেকোনো প্রশ্ন করলে দ্রুত উত্তর পাই, সাপোর্ট টিম খুব আন্তরিক।", True),
    (5, "অনলাইনে পড়েও মনে হয় ক্লাসরুমে বসে আছি। পুরো কোচিংকে ধন্যবাদ।", False),
]

#: Feedback staff add from elsewhere: (name, designation, rating, comment)
STAFF_ADDED = [
    ("মাহমুদুল হক", "অভিভাবক, সিলেট", 5, "ছেলের আইসিটির ভয় কেটে গেছে, নিয়মিত পরীক্ষার রেজাল্ট দেখে নিশ্চিন্ত থাকি।"),
    ("সুমাইয়া আক্তার", "এইচএসসি ২০২৫ (ফেসবুক রিভিউ)", 5, "এক কথায় অসাধারণ! আইসিটিতে A+ পেয়েছি।"),
]

STAFF_DESIGNATIONS = [designation for _, designation, _, _ in STAFF_ADDED]


def _clear():
    Feedback.objects.filter(author__phone__startswith=PHONE_PREFIX).delete()
    Feedback.objects.filter(author__isnull=True, designation__in=STAFF_DESIGNATIONS).delete()
    User.objects.filter(phone__startswith=PHONE_PREFIX).delete()


class Command(BaseCommand):
    help = "Replace the example feedback (course, general, staff-added) and its demo students; local testing only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Only remove the example feedback and its students.")

    @transaction.atomic
    def handle(self, *args, clear=False, **options):
        _clear()
        if clear:
            self.stdout.write("Example feedback removed.")
            return

        courses = list(Course.objects.filter(status=Course.Status.PUBLISHED).order_by("id"))
        if not courses:
            self.stdout.write(self.style.WARNING("No published course to review; only general feedback is added."))
        levels = {level.slug: level for level in ClassLevel.objects.all()}

        students = []
        for index, (name, level, institution) in enumerate(STUDENTS):
            user = User.objects.create_user(phone=f"{PHONE_PREFIX}{index:04d}", name=name, role=User.Role.STUDENT)
            StudentProfile.objects.update_or_create(
                user=user, defaults={"class_level": levels.get(level), "institution": institution}
            )
            students.append(user)

        now = timezone.now()
        written = []

        def settle(feedback, *, status, featured=False, days_ago):
            Feedback.objects.filter(pk=feedback.pk).update(
                status=status, is_featured=featured, created_at=now - timezone.timedelta(days=days_ago)
            )
            written.append(status)

        # Each course gets reviews from a rotating group of students, mostly approved.
        ratings = [5, 5, 4, 5, 3, 4, 5]
        for c, course in enumerate(courses):
            reviewers = [students[(c * 3 + i) % len(students)] for i in range(4 + c % 3)]
            for r, student in enumerate(reviewers):
                Enrollment.objects.get_or_create(course=course, user=student)
                rating = ratings[(c + r) % len(ratings)]
                comments = COURSE_COMMENTS[rating]
                feedback = submit_feedback(
                    user=student, course=course, rating=rating, comment=comments[(c + r) % len(comments)]
                )
                status = Feedback.Status.PENDING if r == 0 else Feedback.Status.APPROVED
                if c == 0 and r == 1:
                    status = Feedback.Status.HIDDEN
                settle(feedback, status=status, days_ago=2 + c * 3 + r * 5)

        for g, (rating, comment, featured) in enumerate(GENERAL_COMMENTS):
            feedback = submit_feedback(user=students[-(g + 1)], rating=rating, comment=comment)
            settle(feedback, status=Feedback.Status.APPROVED, featured=featured, days_ago=10 + g * 7)
        pending = submit_feedback(user=students[0], rating=4, comment="আরও বেশি মডেল টেস্ট চাই, বাকি সব দারুণ।")
        settle(pending, status=Feedback.Status.PENDING, days_ago=1)

        for s, (name, designation, rating, comment) in enumerate(STAFF_ADDED):
            feedback = Feedback.objects.create(
                source=Feedback.Source.GENERAL,
                name=name,
                designation=designation,
                rating=rating,
                comment=comment,
            )
            settle(feedback, status=Feedback.Status.APPROVED, featured=True, days_ago=20 + s * 9)

        counts = {status: written.count(status) for status in Feedback.Status.values}
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(written)} feedback added for {len(courses)} courses and {len(students)} demo students: "
                f"{counts['approved']} approved, {counts['pending']} waiting, {counts['hidden']} hidden."
            )
        )
