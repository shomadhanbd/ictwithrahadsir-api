from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import OrderedModel, TimestampModel


class QuestionBank(TimestampModel, OrderedModel):
    """A folder in the MCQ question bank; folders nest (subject > chapter >
    topic, etc.) and an exam Content links to one folder as its question
    source."""

    title = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def all_questions(self):
        """Questions in this folder and every descendant folder."""
        ids = [self.id]
        frontier = [self.id]
        while frontier:
            child_ids = list(QuestionBank.objects.filter(parent_id__in=frontier).values_list("id", flat=True))
            ids.extend(child_ids)
            frontier = child_ids
        return Question.objects.filter(bank_id__in=ids)


class Question(TimestampModel):
    class Answer(models.TextChoices):
        A = "a", "A"
        B = "b", "B"
        C = "c", "C"
        D = "d", "D"
        E = "e", "E"

    bank = models.ForeignKey(QuestionBank, on_delete=models.CASCADE, related_name="questions")
    question = models.TextField()
    question_image = models.URLField(null=True, blank=True)
    a = models.TextField(null=True, blank=True)
    b = models.TextField(null=True, blank=True)
    c = models.TextField(null=True, blank=True)
    d = models.TextField(null=True, blank=True)
    e = models.TextField(null=True, blank=True)
    answer = models.CharField(max_length=1, choices=Answer.choices)
    answer_image = models.URLField(null=True, blank=True)
    explanation = models.TextField(blank=True)

    source_year = models.CharField(max_length=20, blank=True)
    source_board = models.CharField(max_length=100, blank=True)
    source_topic = models.CharField(max_length=150, blank=True)
    source_chapter = models.CharField(max_length=150, blank=True)
    source_college = models.CharField(max_length=150, blank=True)
    source_subject = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.question[:60]


class Exam(TimestampModel):
    """The configuration of a sittable exam.

    These ten fields used to hang off `courses.Content`, so `assessment`
    owned the question bank and the attempts but not the exam itself. A
    Content of type EXAM now points here for its marks scheme, timing and
    embargo.

    `content` is the primary key on purpose. The public identifier for an
    exam is a Content id in four separate places -- the /exams/<pk>/ route,
    the `exam` block on content detail, the attempt's `exam_id`, and the
    admin's ?exam_id= filter -- so making the one-to-one the PK keeps every
    one of those ids literally correct with no translation anywhere.
    """

    class Mode(models.TextChoices):
        EXAM = "exam", "Exam"
        PRACTICE = "practice", "Practice"
        QUIZ = "quiz", "Quiz"

    content = models.OneToOneField(
        "courses.Content",
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="exam",
    )
    question_bank = models.ForeignKey(
        QuestionBank, on_delete=models.SET_NULL, null=True, blank=True, related_name="exams"
    )
    mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.EXAM)
    total_marks = models.PositiveIntegerField(null=True, blank=True)
    pass_marks = models.PositiveIntegerField(null=True, blank=True)
    positive_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=1)
    negative_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=0)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    result_publish_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Exam({self.pk})"

    @property
    def results_published(self) -> bool:
        """Whether marks, the answer key and the board may be shown yet.

        An unset time means no embargo, so exams that never configured one
        behave exactly as before.
        """
        if self.result_publish_time is None:
            return True
        return timezone.now() >= self.result_publish_time


class ExamAttempt(TimestampModel):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_results")
    marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    positive_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    negative_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    duration = models.PositiveIntegerField(default=0, help_text="Seconds spent on the attempt")
    submitted = models.BooleanField(default=True)
    answers = models.JSONField(default=list, blank=True)
    attachment = models.URLField(null=True, blank=True)

    class Meta:
        ordering = ["-marks", "duration"]
        unique_together = ["exam", "user"]
        indexes = [
            # The leaderboard reads an exam's attempts in this exact order,
            # and the caller's rank is a COUNT over the same three columns.
            models.Index(fields=["exam", "-marks", "duration"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.exam} ({self.marks})"
