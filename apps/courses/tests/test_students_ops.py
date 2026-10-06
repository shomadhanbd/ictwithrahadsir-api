import csv
import io
from unittest.mock import patch

from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.courses.models import Content, ContentCompletion, Course, CourseTeacher, Enrollment, Section
from apps.courses.services import send_expiry_reminders
from apps.identity.models import User


def sms_outbox():
    return patch('apps.courses.services.get_sms_backend')


class ExpiryReminderTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title='HSC ICT', slug='hsc-ict-remind', status='published')
        self.now = timezone.now()

    def enrol(self, valid_till):
        return Enrollment.objects.create(course=self.course, user=make_user(), valid_till=valid_till)

    def test_only_access_ending_soon_is_reminded_once(self):
        soon = self.enrol(self.now + timezone.timedelta(days=2))
        self.enrol(self.now + timezone.timedelta(days=10))
        self.enrol(self.now - timezone.timedelta(days=1))
        self.enrol(None)

        with sms_outbox() as backend:
            self.assertEqual(send_expiry_reminders(days=3), 1)
            self.assertEqual(send_expiry_reminders(days=3), 0)

        backend.return_value.send.assert_called_once()
        phone, message = backend.return_value.send.call_args.args
        self.assertEqual(phone, soon.user.phone)
        self.assertIn('HSC ICT', message)
        self.assertIn('/course/hsc-ict-remind', message)

    def test_a_renewed_end_date_is_reminded_again(self):
        enrolment = self.enrol(self.now + timezone.timedelta(days=1))
        with sms_outbox():
            send_expiry_reminders(days=3)
            Enrollment.objects.filter(pk=enrolment.pk).update(valid_till=self.now + timezone.timedelta(days=2))
            self.assertEqual(send_expiry_reminders(days=3), 1)

    def test_a_failed_send_is_retried_next_run(self):
        self.enrol(self.now + timezone.timedelta(days=1))
        with sms_outbox() as backend:
            backend.return_value.send.side_effect = RuntimeError('down')
            self.assertEqual(send_expiry_reminders(days=3), 0)
            backend.return_value.send.side_effect = None
            self.assertEqual(send_expiry_reminders(days=3), 1)

    def test_two_overlapping_runs_text_a_student_once(self):
        """Both runs listed the enrolment before either marked it; only the first to claim it sends."""
        self.enrol(self.now + timezone.timedelta(days=1))
        listed = list(Enrollment.objects.all())
        with (
            sms_outbox() as backend,
            patch('apps.courses.services.enrollments_due_reminder', side_effect=lambda **_: list(listed)),
        ):
            self.assertEqual(send_expiry_reminders(days=3), 1)
            self.assertEqual(send_expiry_reminders(days=3), 0)
        backend.return_value.send.assert_called_once()

    def test_the_command_has_a_dry_run(self):
        self.enrol(self.now + timezone.timedelta(days=1))
        out = io.StringIO()
        with sms_outbox() as backend:
            call_command('send_expiry_reminders', '--dry-run', stdout=out)
        backend.return_value.send.assert_not_called()
        self.assertIn('1 student(s) would be reminded', out.getvalue())


class StudentsExportTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title='HSC ICT', slug='hsc-ict-export', status='published')
        section = Section.objects.create(course=self.course, title='Ch 1', slug='hsc-ict-export-ch1')
        self.lessons = [
            Content.objects.create(
                course=self.course, section=section, title=f'L{i}', slug=f'export-l{i}', type='video'
            )
            for i in range(4)
        ]
        self.student = make_user(name='Rahim')
        Enrollment.objects.create(course=self.course, user=self.student, payment_type='paid')
        ContentCompletion.objects.create(user=self.student, content=self.lessons[0], course=self.course)
        self.url = reverse('api:courses:admin_course_users_export', args=[self.course.pk])

    def test_admin_downloads_a_csv(self):
        response = self.client.get(self.url, **bearer(make_user(role=User.Role.ADMIN)))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/csv'))
        body = response.content.decode('utf-8')
        self.assertTrue(body.startswith('﻿'))
        header, row = list(csv.reader(io.StringIO(body.lstrip('﻿'))))
        self.assertEqual(header[0], 'Name')
        self.assertEqual((row[0], row[4], row[5], row[6], row[7]), ('Rahim', 'Lifetime', 'Active', 'Paid', '25'))

    def test_a_name_that_is_a_formula_is_exported_as_text(self):
        """A student picks their own name; the admin opens the file in Excel."""
        self.student.name = '=HYPERLINK("http://evil.example","Click")'
        self.student.save()
        response = self.client.get(self.url, **bearer(make_user(role=User.Role.ADMIN)))
        _header, row = list(csv.reader(io.StringIO(response.content.decode('utf-8').lstrip('\ufeff'))))
        self.assertEqual(row[0], '\'=HYPERLINK("http://evil.example","Click")')

    def test_only_the_course_teacher_may_export(self):
        teacher = make_user(role=User.Role.TEACHER)
        self.assertEqual(self.client.get(self.url, **bearer(teacher)).status_code, 403)
        CourseTeacher.objects.create(course=self.course, user=teacher)
        self.assertEqual(self.client.get(self.url, **bearer(teacher)).status_code, 200)
        self.assertEqual(self.client.get(self.url, **bearer(self.student)).status_code, 403)
