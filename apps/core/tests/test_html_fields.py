"""Rich text is cleaned on save, so Django's admin or a shell cannot store script the API would refuse."""

from django.test import TestCase

from apps.communication.models import Notice
from apps.core.testing import next_slug
from apps.courses.models import Content, Course, Section

UNSAFE = '<p>খবর</p><script>steal()</script><a href="javascript:steal()">x</a><img src=x onerror="steal()">'


class HtmlTextFieldTests(TestCase):
    def assert_clean(self, value):
        self.assertIn("<p>খবর</p>", value)
        for unsafe in ("<script", "javascript:", "onerror"):
            self.assertNotIn(unsafe, value)

    def test_a_notice_body_is_cleaned_on_save(self):
        notice = Notice.objects.create(title="Notice", body=UNSAFE)
        notice.refresh_from_db()
        self.assert_clean(notice.body)

    def test_a_course_description_is_cleaned_on_save(self):
        course = Course.objects.create(title="ICT", slug=next_slug("course"), description=UNSAFE)
        course.refresh_from_db()
        self.assert_clean(course.description)

    def test_a_lessons_note_and_video_description_are_cleaned_on_save(self):
        course = Course.objects.create(title="ICT", slug=next_slug("course"))
        section = Section.objects.create(course=course, title="Ch1")
        lesson = Content.objects.create(
            course=course, section=section, title="Lesson", note_body=UNSAFE, video_description=UNSAFE
        )
        lesson.refresh_from_db()
        self.assert_clean(lesson.note_body)
        self.assert_clean(lesson.video_description)

    def test_editing_a_saved_row_cleans_it_again(self):
        notice = Notice.objects.create(title="Notice", body="<p>safe</p>")
        notice.body = UNSAFE
        notice.save(update_fields=["body"])
        notice.refresh_from_db()
        self.assert_clean(notice.body)

    def test_safe_formatting_is_kept(self):
        body = "<h2>শিরোনাম</h2><p><strong>bold</strong></p><ul><li>one</li></ul>"
        self.assertEqual(Notice.objects.create(title="Notice", body=body).body, body)
