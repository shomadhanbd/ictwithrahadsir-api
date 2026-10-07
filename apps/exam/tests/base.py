"""Shared fixtures for the exam tests."""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APITestCase

from apps.academic.models import Chapter, ClassLevel, Group, Subject
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Content, Course, Enrollment, Section
from apps.exam.models import Exam, ExamSection, ExamSectionQuestion
from apps.identity.models import User
from apps.question.models import Question, QuestionBlock, QuestionOption, QuestionSet

EXAMS_URL = reverse("api:exam:admin_exam_list")
SECTIONS_URL = reverse("api:exam:admin_exam_section_list")
BLOCKS_URL = reverse("api:question:admin_question_block_list")


def detail(resource, pk):
    return reverse(f"api:exam:admin_{resource}_detail", args=[pk])


def section_questions(pk):
    return reverse("api:exam:admin_exam_section_question_bulk", args=[pk])


def block_detail(pk):
    return reverse("api:question:admin_question_block_detail", args=[pk])


class ExamTestCase(TestCase):
    def setUp(self):
        self.admin = make_user(role=User.Role.ADMIN)
        self.teacher = make_user(role=User.Role.TEACHER)
        self.other_teacher = make_user(role=User.Role.TEACHER)

        self.auth = bearer(self.admin)
        self.teacher_auth = bearer(self.teacher)
        self.other_auth = bearer(self.other_teacher)

        self.hsc = ClassLevel.objects.create(name="এইচএসসি", slug="hsc")
        self.ssc = ClassLevel.objects.create(name="এসএসসি", slug="ssc")
        self.science = Group.objects.create(name="বিজ্ঞান", slug="science")
        self.ict = Subject.objects.create(name="ICT", class_level=self.hsc, group=self.science, slug="ict-hsc")
        self.physics = Subject.objects.create(
            name="Physics", class_level=self.hsc, group=self.science, slug="physics-hsc"
        )
        self.chapter = Chapter.objects.create(
            slug=next_slug("chapter"), name="Number Systems", subject=self.ict, chapter_number=1
        )

    def exam(self, **overrides):
        return Exam.objects.create(
            **{"title": "HSC ICT মডেল টেস্ট", "created_by": self.admin, "total_marks": 100, **overrides}
        )

    def section(self, exam=None, **overrides):
        return ExamSection.objects.create(
            **{
                "exam": exam or self.exam(),
                "title": "MCQ",
                "question_type": ExamSection.Type.MCQ,
                "subject": self.ict,
                "marks": 30,
                "marks_per_question": 1,
                **overrides,
            }
        )

    def mcq_block(self, subject=None):
        """A standalone block whose single question is an MCQ."""
        block = QuestionBlock.objects.create(subject=subject or self.ict)
        Question.objects.create(block=block, question_type=Question.Type.MCQ, prompt_content="2 + 2 = ?")
        return block

    def cq_block(self, subject=None):
        """A group block: one stimulus, four creative-question parts."""
        block = QuestionBlock.objects.create(subject=subject or self.ict, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="উদ্দীপক")
        for order, label in enumerate(["ক", "খ", "গ", "ঘ"]):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.CQ,
                label=label,
                order_in_set=order,
                prompt_content=f"part {label}",
            )
        return block

    def mcq_passage(self, parts=3, subject=None):
        """A group block: one passage (উদ্দীপক), N MCQs under it."""
        block = QuestionBlock.objects.create(subject=subject or self.ict, kind=QuestionBlock.Kind.GROUP)
        question_set = QuestionSet.objects.create(block=block, stimulus_content="একটি অনুচ্ছেদ")
        for order in range(parts):
            Question.objects.create(
                question_set=question_set,
                question_type=Question.Type.MCQ,
                order_in_set=order,
                prompt_content=f"passage question {order + 1}",
            )
        block.refresh_from_db()
        return block

    def mixed_block(self):
        """A group whose parts disagree, so neither section type accepts it."""
        block = self.cq_block()
        block.question_set.questions.filter(label="ক").update(question_type=Question.Type.MCQ)
        return block

    def empty_block(self):
        """A block with no question yet."""
        return QuestionBlock.objects.create(subject=self.ict)


LESSONS_URL = reverse("api:courses:admin_content_list")


def url(name, *args):
    return reverse(f"api:exam:{name}", args=args)


class CourseExamTestCase(APITestCase):
    def setUp(self):
        self.admin = make_user(role=User.Role.ADMIN)
        self.student = make_user(name="Student One")
        self.other = make_user(name="Student Two")
        self.admin_auth = bearer(self.admin)
        self.student_auth = bearer(self.student)

        level = ClassLevel.objects.create(name="HSC", slug="hsc")
        group = Group.objects.create(name="Science", slug="science")
        self.subject = Subject.objects.create(name="ICT", class_level=level, group=group, slug="ict-hsc")
        self.course = Course.objects.create(title="ICT", slug="ict", status="published")
        self.chapter = Section.objects.create(course=self.course, title="Ch 1")
        Enrollment.objects.create(course=self.course, user=self.student)
        Enrollment.objects.create(course=self.course, user=self.other)

    def lesson(self, **fields):
        return Content.objects.create(
            course=self.course,
            section=self.chapter,
            type="exam",
            title=fields.pop("title", "Model test"),
            **fields,
        )

    def mcq(self, correct=0, options=4, multiple=False):
        block = QuestionBlock.objects.create(subject=self.subject)
        question = Question.objects.create(
            block=block,
            question_type=Question.Type.MCQ,
            prompt_content="?",
            explanation="Because.",
            metadata={"select_mode": "multiple"} if multiple else {},
        )
        for i in range(options):
            QuestionOption.objects.create(
                question=question,
                content=f"option {i}",
                position=i,
                is_correct=(i in correct) if isinstance(correct, (list, tuple)) else i == correct,
            )
        return block, question

    def published_exam(self, questions=3, negative="0.25", **exam_fields):
        """A course exam with one MCQ part of `questions` one-mark questions."""
        exam = self.lesson().exam
        for field, value in {"total_marks": questions, **exam_fields}.items():
            setattr(exam, field, value)
        exam.save()
        section = ExamSection.objects.create(
            exam=exam,
            title="MCQ",
            question_type="mcq",
            subject=self.subject,
            marks=questions,
            marks_per_question=1,
            negative_marks=Decimal(negative),
        )
        self.questions = []
        for order in range(questions):
            block, question = self.mcq(correct=0)
            ExamSectionQuestion.objects.create(section=section, block=block, marks=1, order=order)
            self.questions.append(question)
        exam.status = Exam.Status.PUBLISHED
        exam.save()
        return exam

    def option(self, question, position):
        return question.options.get(position=position).pk
