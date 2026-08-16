from django.conf import settings
from django.db import models

from apps.core.models import OrderedModel, TimestampModel


class McqStore(TimestampModel, OrderedModel):
    """A folder in the MCQ question bank; folders nest (subject > chapter >
    topic, etc.) and an exam Content links to one folder as its question
    source."""

    title = models.CharField(max_length=255)
    mcq_store = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )

    class Meta:
        ordering = ["order", "title"]

    def __str__(self):
        return self.title

    def all_questions(self):
        """Questions in this folder and every descendant folder."""
        ids = [self.id]
        frontier = [self.id]
        while frontier:
            child_ids = list(McqStore.objects.filter(mcq_store_id__in=frontier).values_list("id", flat=True))
            ids.extend(child_ids)
            frontier = child_ids
        return McqQuestion.objects.filter(mcq_store_id__in=ids)


class McqQuestion(TimestampModel):
    class Answer(models.TextChoices):
        A = "a", "A"
        B = "b", "B"
        C = "c", "C"
        D = "d", "D"
        E = "e", "E"

    mcq_store = models.ForeignKey(McqStore, on_delete=models.CASCADE, related_name="questions")
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


class ExamResult(TimestampModel):
    content = models.ForeignKey(
        "courses.Content", on_delete=models.CASCADE, related_name="exam_results"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="exam_results"
    )
    marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    positive_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    negative_marks = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    duration = models.PositiveIntegerField(default=0, help_text="Seconds spent on the attempt")
    submitted = models.BooleanField(default=True)
    answers = models.JSONField(default=list, blank=True)
    attachment = models.URLField(null=True, blank=True)

    class Meta:
        ordering = ["-marks", "duration"]
        unique_together = ["content", "user"]

    def __str__(self):
        return f"{self.user} - {self.content} ({self.marks})"
