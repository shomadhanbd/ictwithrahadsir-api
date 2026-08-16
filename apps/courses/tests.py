"""Contract tests for the course catalogue, content gating and enrolment."""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.courses.models import (
    Content,
    Course,
    CourseCategory,
    CoursePrice,
    CourseUser,
    Section,
)

COURSE_LIST_URL = reverse('api:courses:v1:course_list')
CATEGORY_LIST_URL = reverse('api:courses:v1:course_category_list')
MY_COURSE_URL = reverse('api:courses:v1:my_course_list')
ATTACH_URL = reverse('api:courses:v1:admin_course_user_attach')
UPDATE_URL = reverse('api:courses:v1:admin_course_user_update')
REMOVE_URL = reverse('api:courses:v1:admin_course_user_remove')


class CatalogueTests(APITestCase):
    def setUp(self):
        self.category = CourseCategory.objects.create(title='HSC', slug='hsc')
        self.course = Course.objects.create(
            title='ICT Full', slug='ict-full', active=True, is_online=True
        )
        self.course.categories.add(self.category)
        Course.objects.create(title='Archived', slug='archived', active=False)
        Course.objects.create(title='Offline', slug='offline', active=True, is_online=False)

    def test_only_active_courses_are_listed(self):
        titles = [c['title'] for c in self.client.get(COURSE_LIST_URL).json()['data']]
        self.assertNotIn('Archived', titles)
        self.assertEqual(len(titles), 2)

    def test_courses_filter_by_online_flag(self):
        body = self.client.get(COURSE_LIST_URL, {'is_online': 'true'}).json()
        self.assertEqual([c['title'] for c in body['data']], ['ICT Full'])

    def test_courses_filter_by_category_slug(self):
        body = self.client.get(COURSE_LIST_URL, {'category_slug': 'hsc'}).json()
        self.assertEqual([c['title'] for c in body['data']], ['ICT Full'])

    def test_course_detail_is_fetched_by_slug(self):
        url = reverse('api:courses:v1:course_detail', args=['ict-full'])
        self.assertEqual(self.client.get(url).json()['title'], 'ICT Full')

    def test_inactive_course_detail_is_404(self):
        url = reverse('api:courses:v1:course_detail', args=['archived'])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_categories_are_top_level_only(self):
        CourseCategory.objects.create(title='HSC 26', slug='hsc-26', category=self.category)
        body = self.client.get(CATEGORY_LIST_URL).json()
        self.assertEqual([c['title'] for c in body['data']], ['HSC'])


class ContentAccessTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            phone='01810300001', name='Student', password='Str0ngPass!23'
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        self.course = Course.objects.create(title='ICT', slug='ict')
        self.section = Section.objects.create(course=self.course, title='Ch1', slug='ict-ch1')
        self.paid = Content.objects.create(
            course=self.course, section=self.section, title='Paid lesson',
            slug='ict-paid', type=Content.Type.VIDEO, paid=True,
        )
        self.free = Content.objects.create(
            course=self.course, section=self.section, title='Free lesson',
            slug='ict-free', type=Content.Type.VIDEO, paid=False,
        )

    def url(self, slug):
        return reverse('api:courses:v1:content_detail', args=[slug])

    def test_free_content_is_open_to_anonymous(self):
        self.assertEqual(self.client.get(self.url('ict-free')).status_code, 200)

    def test_paid_content_is_closed_to_anonymous(self):
        self.assertEqual(self.client.get(self.url('ict-paid')).status_code, 403)

    def test_paid_content_is_closed_without_enrolment(self):
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 403)

    def test_enrolment_opens_paid_content(self):
        CourseUser.objects.create(course=self.course, user=self.student)
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 200)

    def test_expired_enrolment_closes_paid_content(self):
        CourseUser.objects.create(
            course=self.course, user=self.student,
            valid_till=timezone.now() - timezone.timedelta(days=1),
        )
        self.assertEqual(self.client.get(self.url('ict-paid'), **self.auth).status_code, 403)

    def test_unknown_content_is_404(self):
        self.assertEqual(self.client.get(self.url('nope')).status_code, 404)


class MyCoursesTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            phone='01810300002', name='Student', password='Str0ngPass!23'
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        self.enrolled = Course.objects.create(title='Mine', slug='mine')
        Course.objects.create(title='Theirs', slug='theirs')
        CourseUser.objects.create(course=self.enrolled, user=self.student)

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get(MY_COURSE_URL).status_code, 401)

    def test_only_enrolled_courses_are_returned(self):
        body = self.client.get(MY_COURSE_URL, **self.auth).json()
        self.assertEqual([c['title'] for c in body['data']], ['Mine'])


class AdminEnrolmentTests(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone='01710300001', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.student = User.objects.create_user(
            phone='01810300003', name='Student', password='Str0ngPass!23'
        )
        self.course = Course.objects.create(title='ICT', slug='ict')
        self.price = CoursePrice.objects.create(
            priceable_type=CoursePrice.PRICEABLE_COURSE,
            priceable_id=self.course.id,
            title='Full',
            amount=Decimal('1500'),
            validity_type=CoursePrice.ValidityType.RELATIVE,
            validity_duration=30,
        )

    def test_attach_by_slug(self):
        response = self.client.post(
            ATTACH_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(CourseUser.objects.filter(course=self.course, user=self.student).exists())

    def test_attach_by_numeric_id(self):
        response = self.client.post(
            ATTACH_URL, {'slugOrId': str(self.course.pk), 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_attaching_with_a_price_sets_validity_and_payment_type(self):
        self.client.post(
            ATTACH_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json', **self.auth,
        )
        enrolment = CourseUser.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrolment.payment_type, CourseUser.PaymentType.PAID)
        self.assertIsNotNone(enrolment.valid_till)

    def test_a_price_from_another_course_is_rejected(self):
        other = Course.objects.create(title='Other', slug='other')
        response = self.client.post(
            ATTACH_URL,
            {'slugOrId': other.slug, 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_attach_requires_a_valid_course_and_user(self):
        response = self.client.post(
            ATTACH_URL, {'slugOrId': 'ghost', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_update_changes_payment_type(self):
        CourseUser.objects.create(course=self.course, user=self.student)
        response = self.client.post(
            UPDATE_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'payment_type': 'paid'},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CourseUser.objects.get(course=self.course, user=self.student).payment_type, 'paid'
        )

    def test_update_on_a_missing_enrolment_is_404(self):
        response = self.client.post(
            UPDATE_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def test_remove_deletes_the_enrolment(self):
        CourseUser.objects.create(course=self.course, user=self.student)
        response = self.client.post(
            REMOVE_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertTrue(response.json()['ok'])
        self.assertFalse(CourseUser.objects.exists())

    def test_remove_reports_false_when_nothing_matched(self):
        response = self.client.post(
            REMOVE_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertFalse(response.json()['ok'])

    def test_students_cannot_attach(self):
        student_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        response = self.client.post(
            ATTACH_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **student_auth,
        )
        self.assertEqual(response.status_code, 403)


class AdminContentToggleTests(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone='01710300002', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        course = Course.objects.create(title='ICT', slug='ict')
        section = Section.objects.create(course=course, title='Ch1', slug='ict-ch1')
        self.content = Content.objects.create(
            course=course, section=section, title='Lesson', slug='ict-lesson',
            type=Content.Type.VIDEO, active=True, paid=True,
        )

    def url(self):
        return reverse('api:courses:v1:admin_content_toggle', args=[self.content.pk])

    def test_active_is_flipped(self):
        self.client.get(self.url(), {'action': 'active'}, **self.auth)
        self.content.refresh_from_db()
        self.assertFalse(self.content.active)

    def test_paid_is_flipped(self):
        self.client.get(self.url(), {'action': 'paid'}, **self.auth)
        self.content.refresh_from_db()
        self.assertFalse(self.content.paid)

    def test_an_unknown_action_is_rejected(self):
        response = self.client.get(self.url(), {'action': 'delete'}, **self.auth)
        self.assertEqual(response.status_code, 422)
        self.content.refresh_from_db()
        self.assertTrue(self.content.active)
