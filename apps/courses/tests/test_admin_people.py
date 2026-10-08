from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.courses.models import (
    Course,
    Enrollment,
)
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

ENROLLMENT_URL = reverse('api:courses:admin_enrollment')


class AdminEnrolmentTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.student = make_user()
        self.course = Course.objects.create(title='ICT', slug='ict')

    def test_attach_by_slug(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Enrollment.objects.filter(course=self.course, user=self.student).exists())

    def enrol_free(self, **body):
        payload = {'slugOrId': str(self.course.pk), 'user_id': self.student.pk, **body}
        return self.client.post(ENROLLMENT_URL, payload, format='json', **self.auth)

    def test_running_paid_access_is_not_overwritten_by_free_access(self):
        until = timezone.now() + timezone.timedelta(days=200)
        Enrollment.objects.create(
            course=self.course, user=self.student, payment_type=Enrollment.PaymentType.PAID, valid_till=until
        )

        response = self.enrol_free(valid_till=(timezone.now() + timezone.timedelta(days=20)).isoformat())

        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn('Edit enrolment', response.json()['errors']['user_id'][0])
        enrollment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertEqual((enrollment.payment_type, enrollment.valid_till), (Enrollment.PaymentType.PAID, until))

    def test_lifetime_access_is_not_overwritten(self):
        Enrollment.objects.create(course=self.course, user=self.student, valid_till=None)
        response = self.enrol_free()
        self.assertEqual(response.status_code, 422)
        self.assertIn('for life', response.json()['errors']['user_id'][0])

    def test_access_that_has_ended_is_granted_again_as_free(self):
        Enrollment.objects.create(
            course=self.course,
            user=self.student,
            payment_type=Enrollment.PaymentType.PAID,
            valid_till=timezone.now() - timezone.timedelta(days=1),
        )
        until = timezone.now() + timezone.timedelta(days=30)

        self.assertEqual(self.enrol_free(valid_till=until.isoformat()).status_code, 201)

        enrollment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrollment.payment_type, Enrollment.PaymentType.FREE)
        self.assertAlmostEqual(enrollment.valid_till, until, delta=timezone.timedelta(seconds=1))

    def test_attach_by_numeric_id(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': str(self.course.pk), 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_a_manual_grant_is_free_and_lifetime_by_default(self):
        self.client.post(ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk}, format='json', **self.auth)
        enrolment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.FREE)
        self.assertIsNone(enrolment.valid_till)

    def test_a_manual_grant_takes_an_end_date(self):
        ends = timezone.now() + timezone.timedelta(days=30)
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'valid_till': ends.isoformat()},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        enrolment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertAlmostEqual(enrolment.valid_till, ends, delta=timezone.timedelta(seconds=1))

    def test_an_end_date_in_the_past_is_rejected(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'valid_till': '2020-01-01T00:00:00Z'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('valid_till', response.json()['errors'])

    def test_attaching_an_unknown_user_is_a_validation_error(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': 999999},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('user_id', response.json()['errors'])

    def test_attach_requires_a_valid_course_and_user(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ghost', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_update_changes_payment_type(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.patch(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'payment_type': 'paid'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Enrollment.objects.get(course=self.course, user=self.student).payment_type, 'paid')

    def test_update_rejects_an_unknown_payment_type(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.patch(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'payment_type': 'bitcoin'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Enrollment.objects.get(course=self.course, user=self.student).payment_type, 'free')

    def test_update_rejects_a_malformed_date(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.patch(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'valid_till': 'next tuesday'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIsNone(Enrollment.objects.get(course=self.course, user=self.student).valid_till)

    def test_update_on_a_missing_enrolment_is_404(self):
        response = self.client.patch(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def test_remove_deletes_the_enrolment(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.delete(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertTrue(response.json()['ok'])
        self.assertFalse(Enrollment.objects.exists())

    def test_remove_reports_false_when_nothing_matched(self):
        response = self.client.delete(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertFalse(response.json()['ok'])

    def test_students_cannot_attach(self):
        student_auth = bearer(self.student)
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **student_auth,
        )
        self.assertEqual(response.status_code, 403)


class CourseTeacherTests(APITestCase):
    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.course = Course.objects.create(status='published', title='ICT Full', slug='ict-full')
        self.other = Course.objects.create(status='published', title='Other', slug='other')

        self.teacher = make_user(role=User.Role.TEACHER, name='Rahad Sir')
        TeacherProfile.objects.create(user=self.teacher, designation='Founder')
        self.url = reverse('api:courses:admin_course_teacher_list')

    def _assign(self, course, **extra):
        return self.client.post(
            self.url,
            {'course_id': course.pk, 'user_id': self.teacher.pk, **extra},
            format='json',
            **self.auth,
        )

    def test_assigning_a_teacher_reads_their_details_through_the_roster(self):
        response = self._assign(self.course, commission='25.00')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['name'], 'Rahad Sir')
        self.assertEqual(response.data['designation'], 'Founder')

    def test_a_teacher_cannot_be_assigned_to_one_course_twice(self):
        self._assign(self.course)
        response = self._assign(self.course)
        self.assertEqual(response.status_code, 422)

    def test_the_course_id_filter_narrows_the_list(self):
        self._assign(self.course)
        self._assign(self.other)

        body = self.client.get(self.url, {'course_id': self.course.pk}, **self.auth).json()

        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['course_id'], self.course.pk)

    def test_only_a_teacher_can_be_assigned(self):
        """A plain student assigned to a course would gain its admin scope."""
        student = make_user()

        response = self.client.post(
            self.url,
            {'course_id': self.course.pk, 'user_id': student.pk},
            format='json',
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('user_id', response.json()['errors'])
