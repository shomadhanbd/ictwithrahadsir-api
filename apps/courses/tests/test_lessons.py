from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.courses.models import (
    Content,
    Course,
    CourseMaterial,
    Enrollment,
    Section,
)


class ContentAccessTests(APITestCase):
    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.course = Course.objects.create(status='published', title='ICT', slug='ict')
        self.section = Section.objects.create(course=self.course, title='Ch1', slug='ict-ch1')
        self.paid = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Paid lesson',
            slug='ict-paid',
            type=Content.Type.VIDEO,
            paid=True,
        )
        self.free = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Free lesson',
            slug='ict-free',
            type=Content.Type.VIDEO,
            paid=False,
        )

    def url(self, slug):
        return reverse('api:courses:content_detail', args=[slug])

    def test_free_content_is_open_to_anonymous(self):
        self.assertEqual(self.client.get(self.url('ict-free')).status_code, 200)

    def test_paid_content_is_closed_to_anonymous(self):
        self.assertEqual(self.client.get(self.url('ict-paid')).status_code, 403)

    def test_paid_content_is_closed_without_enrolment(self):
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 403)

    def test_enrolment_opens_paid_content(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 200)

    def test_expired_enrolment_closes_paid_content(self):
        Enrollment.objects.create(
            course=self.course,
            user=self.student,
            valid_till=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 403)

    def test_unknown_content_is_404(self):
        self.assertEqual(self.client.get(self.url('nope')).status_code, 404)

    def test_each_type_fills_only_its_own_block(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        when = timezone.now() + timezone.timedelta(days=2)
        lessons = {
            'note': {'note_body': '<p>Read me</p>'},
            'pdf': {'pdf_file': 'https://files.example.com/secret.pdf'},
            'link': {'link_url': 'https://example.com'},
            'live': {'live_url': 'https://meet.example.com/x', 'live_scheduled_at': when},
        }
        blocks = ('video', 'note', 'pdf', 'link', 'live')
        for kind, fields in lessons.items():
            with self.subTest(kind=kind):
                Content.objects.create(
                    course=self.course, section=self.section, title=kind, slug=f'ict-{kind}', type=kind, **fields
                )
                body = self.client.get(self.url(f'ict-{kind}'), **self.auth).json()
                self.assertEqual([b for b in blocks if body[b] is not None], [kind])

        self.assertEqual(self.client.get(self.url('ict-note'), **self.auth).json()['note'], {'body': '<p>Read me</p>'})
        self.assertEqual(self.client.get(self.url('ict-pdf'), **self.auth).json()['pdf'], {'has_file': True})
        live = self.client.get(self.url('ict-live'), **self.auth).json()['live']
        self.assertEqual(live['url'], 'https://meet.example.com/x')
        self.assertIsNotNone(live['scheduled_at'])


class LessonReleaseTests(APITestCase):
    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.course = Course.objects.create(status='published', title='ICT', slug='ict-release')
        section = Section.objects.create(course=self.course, title='Ch1')
        Enrollment.objects.create(course=self.course, user=self.student)
        self.later = timezone.now() + timezone.timedelta(days=2)
        self.lesson = Content.objects.create(
            course=self.course,
            section=section,
            title='Next week',
            slug='next-week',
            type=Content.Type.VIDEO,
            paid=False,
            available_from=self.later,
        )

    def detail(self):
        return self.client.get(reverse('api:courses:content_detail', args=['next-week']), **self.auth)

    def test_an_unreleased_lesson_cannot_be_opened(self):
        response = self.detail()
        self.assertEqual(response.status_code, 403)
        self.assertIn('Available from', response.json()['message'])

    def test_a_released_lesson_opens(self):
        Content.objects.filter(pk=self.lesson.pk).update(available_from=timezone.now() - timezone.timedelta(hours=1))
        self.assertEqual(self.detail().status_code, 200)

    def test_an_unreleased_lesson_is_still_listed_on_the_course(self):
        body = self.client.get(reverse('api:courses:course_detail', args=['ict-release'])).json()
        lesson = body['curriculum'][0]['contents'][0]
        self.assertEqual(lesson['slug'], 'next-week')
        self.assertIsNotNone(lesson['available_from'])

    def test_an_unreleased_lesson_cannot_be_marked_complete(self):
        response = self.client.post(
            reverse('api:courses:course_progress', args=['ict-release']),
            {'content_id': self.lesson.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)


class CourseMaterialListTests(APITestCase):
    """Course materials follow the lessons' enrolment rule, expiry included."""

    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.course = Course.objects.create(title='ICT', slug='ict-materials', status='published')
        CourseMaterial.objects.create(
            course=self.course,
            title='Lecture sheet',
            type='pdf',
        )

    def url(self, slug=None):
        return reverse('api:courses:course_material_list', args=[slug or self.course.slug])

    def test_an_anonymous_visitor_is_rejected(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def test_a_student_without_an_enrolment_is_rejected(self):
        response = self.client.get(self.url(), **self.auth)
        self.assertEqual(response.status_code, 403)

    def test_an_enrolled_student_gets_the_materials(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.get(self.url(), **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['title'], 'Lecture sheet')

    def test_an_expired_enrolment_loses_them(self):
        Enrollment.objects.create(
            course=self.course,
            user=self.student,
            valid_till=timezone.now() - timezone.timedelta(days=1),
        )
        response = self.client.get(self.url(), **self.auth)
        self.assertEqual(response.status_code, 403)

    def test_an_unknown_course_is_a_404(self):
        Enrollment.objects.create(course=self.course, user=self.student)
        response = self.client.get(self.url('no-such-course'), **self.auth)
        self.assertEqual(response.status_code, 404)
