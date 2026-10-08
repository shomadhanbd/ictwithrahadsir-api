from datetime import date
from io import BytesIO

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from PIL import Image, ImageDraw, ImageFont

from apps.academic.models import ClassLevel, Group, Subject
from apps.billing.models import Payment, Product
from apps.courses.models import Content, ContentCompletion, Course, CourseTeacher, Routine, Section
from apps.demo.test_courses import COURSES, FAQS, HIGHLIGHTS, OUTCOMES, STUDENT_NAME, VIDEO
from apps.exam.models import Exam, ExamSection
from apps.exam.services.sections import set_section_blocks
from apps.identity.models import User
from apps.question.models import QuestionBlock
from apps.uploads.links import public_link

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
DAY = timezone.timedelta(days=1)


def _cover(slug, title, colors) -> str:
    """A 16:9 gradient cover with the course's title, stored like an upload; returns its link."""
    width, height = 1280, 720
    start, end = (tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in colors)
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for x in range(width):
        t = x / width
        draw.line([(x, 0), (x, height)], fill=tuple(round(a + (b - a) * t) for a, b in zip(start, end, strict=True)))
    try:
        big, small = ImageFont.truetype(FONT, 84), ImageFont.truetype(FONT, 34)
    except OSError:
        big, small = ImageFont.load_default(84), ImageFont.load_default(34)
    words, lines = title.split(), [""]
    for word in words:
        trial = f"{lines[-1]} {word}".strip()
        if draw.textlength(trial, font=big) > width - 160 and lines[-1]:
            lines.append(word)
        else:
            lines[-1] = trial
    y = height / 2 - len(lines) * 50
    for line in lines:
        draw.text((80, y), line, font=big, fill="white")
        y += 100
    draw.text((80, height - 110), "ICT with Rahad Sir", font=small, fill=(255, 255, 255, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    name = f"uploads/image/test-courses/{slug}.png"
    if default_storage.exists(name):
        default_storage.delete(name)
    return public_link(default_storage.save(name, ContentFile(buffer.getvalue())))


class Command(BaseCommand):
    help = "Replace the five test courses (all deliveries, lesson types and package kinds); local testing only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Only remove the test courses.")

    def handle(self, *args, clear=False, **options):
        self._clear()
        if clear:
            self.stdout.write("Test courses removed.")
            return

        student = User.objects.filter(name__startswith=STUDENT_NAME).first()
        if student is None:
            raise CommandError(f"No user named “{STUDENT_NAME}…” to enrol.")
        teacher = User.objects.filter(teacher__isnull=False).first()
        mcqs = iter(QuestionBlock.objects.filter(subject__slug="ict-hsc-general", kind="standalone").order_by("-id"))
        ict = Subject.objects.filter(slug="ict-hsc-general").first()

        for spec in COURSES:
            course = self._course(spec)
            if teacher:
                CourseTeacher.objects.create(course=course, user=teacher)
            lessons = self._lessons(course, spec, mcqs, ict)
            if "enroll" in spec:
                self._enrol(student, course, spec, lessons)
            self.stdout.write(f"  {course.title} — {len(lessons)} lessons")
        self.stdout.write(self.style.SUCCESS(f"5 test courses added; {student.name} is enrolled in 3 (one expired)."))

    def _clear(self):
        slugs = [spec["slug"] for spec in COURSES]
        products = Product.objects.filter(product_id__in=slugs)
        Payment.objects.filter(product__in=products).delete()
        products.delete()
        Exam.objects.filter(lesson__course__slug__in=slugs).delete()
        Course.objects.filter(slug__in=slugs).delete()

    def _course(self, spec) -> Course:
        now = timezone.now()
        cover = _cover(spec["slug"], spec["title"], spec["colors"])
        course = Course.objects.create(
            slug=spec["slug"],
            title=spec["title"],
            subtitle=spec["subtitle"],
            summary=spec["subtitle"],
            description=f"<p>{spec['subtitle']}। এটি পরীক্ষার জন্য তৈরি একটি ডেমো কোর্স।</p>",
            status=Course.Status.PUBLISHED,
            published_at=now,
            difficulty=spec["difficulty"],
            delivery=spec["delivery"],
            is_online=spec["is_online"],
            language="bn",
            duration=spec["duration"],
            fake_student_count=120,
            class_level=ClassLevel.objects.get(slug=spec["level"]),
            group=Group.objects.get(slug=spec["group"]),
            starts_on=(now + spec["starts_in"] * DAY).date() if "starts_in" in spec else None,
            ends_on=(now + spec["ends_in"] * DAY).date() if "ends_in" in spec else None,
            enrollment_deadline=now + spec["enrollment_deadline_in"] * DAY
            if "enrollment_deadline_in" in spec
            else None,
            thumbnail=cover,
            banner=cover,
            promo_video=VIDEO,
            learning_outcomes=[{"title": text, "icon": "circle-check"} for text in OUTCOMES],
            highlights=[{"title": text, "description": "", "icon": "star"} for text in HIGHLIGHTS],
            faqs=[{"question": q, "answer": a} for q, a in FAQS],
            target_audience=[{"title": f"{spec['level'].upper()} শিক্ষার্থী"}],
            requirements=[{"title": "মোবাইল বা কম্পিউটার ও ইন্টারনেট"}],
        )
        for title in spec.get("routines", []):
            Routine.objects.create(course=course, title=title, link="")

        package = spec["package"]
        product = Product.objects.create(
            product_id=spec["slug"],
            title=package["title"],
            price=package["price"],
            base_price=package["base_price"],
            access_days=package.get("access_days"),
            access_ends_on=date.fromisoformat(package["access_ends_on"]) if "access_ends_on" in package else None,
            discount_ends_at=now + package["discount_days"] * DAY if "discount_days" in package else None,
        )
        product.courses.set([course])
        return course

    def _lessons(self, course, spec, mcqs, ict) -> list[Content]:
        now = timezone.now()
        lessons = []
        for chapter_title, items in spec["chapters"]:
            section = Section.objects.create(course=course, title=chapter_title)
            for kind, title, extra in items:
                fields = {"paid": not extra.get("free", False)}
                if "release" in extra:
                    fields["available_from"] = now + extra["release"] * DAY
                if kind == "video":
                    fields.update(video_source="youtube", video_link=VIDEO, video_embedded=True)
                elif kind == "note":
                    fields["note_body"] = f"<h3>{title}</h3><p>এই নোটে অধ্যায়ের মূল বিষয়গুলো সংক্ষেপে দেওয়া আছে।</p>"
                elif kind == "pdf":
                    fields["pdf_file"] = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
                elif kind == "link":
                    fields["link_url"] = "https://www.w3schools.com/"
                elif kind == "live":
                    fields.update(
                        live_url="https://meet.google.com/abc-defg-hij",
                        live_scheduled_at=now + extra.get("live_in", 1) * DAY,
                    )
                lesson = Content.objects.create(course=course, section=section, title=title, type=kind, **fields)
                if kind == "exam" and extra.get("publish") and ict:
                    self._publish_exam(lesson, extra["publish"], mcqs, ict)
                lessons.append(lesson)
        return lessons

    def _publish_exam(self, lesson, count, mcqs, ict):
        exam = Exam.objects.get(lesson=lesson)
        exam.duration_minutes = 15
        exam.pass_marks = max(1, count // 2)
        exam.max_attempts = 3
        exam.save()
        section = ExamSection.objects.create(
            exam=exam, title="MCQ", question_type="mcq", subject=ict, marks=count, marks_per_question=1
        )
        set_section_blocks(section, [next(mcqs) for _ in range(count)])
        exam.status = Exam.Status.PUBLISHED
        exam.save()

    def _enrol(self, student, course, spec, lessons):
        plan = spec["enroll"]
        ends = timezone.now() + plan["ends_in_days"] * DAY if plan["ends_in_days"] is not None else None
        product = Product.objects.get(product_id=spec["slug"])
        # A paid purchase grants the access, as a real cash sale would.
        Payment.objects.create(
            user=student,
            product=product,
            amount=product.current_price,
            status=Payment.Status.VALID,
            method=Payment.Method.CASH,
            # Bought when the access began: an expired purchase is dated back to its start.
            transaction_date=(ends - 90 * DAY) if ends and ends < timezone.now() else timezone.now() - 20 * DAY,
            access_until=ends,
        )
        open_lessons = [lesson for lesson in lessons if lesson.type != "exam"]
        done = open_lessons if plan["done"] == "all" else open_lessons[: plan["done"]]
        for lesson in done:
            ContentCompletion.objects.get_or_create(user=student, content=lesson)
