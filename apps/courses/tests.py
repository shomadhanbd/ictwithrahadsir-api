"""Contract tests for the course catalogue, content gating and enrolment."""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
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
ENROLLMENT_URL = reverse('api:courses:v1:admin_enrollment')


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


class CourseListQueryCountTests(APITestCase):
    """Serialising a course used to cost 11 queries of its own, so a full
    page ran ~170 and the paginator's per_page=200 ceiling meant ~2,200.
    The cost must not scale with the number of courses.
    """

    def make_courses(self, count):
        for i in range(count):
            course = Course.objects.create(title=f'Course {i}', slug=f'course-{i}')
            section = Section.objects.create(
                course=course, title='Ch1', slug=f'course-{i}-ch1'
            )
            for j, content_type in enumerate(
                [Content.Type.VIDEO, Content.Type.EXAM, Content.Type.NOTE]
            ):
                Content.objects.create(
                    course=course, section=section, title=f'C{j}',
                    slug=f'course-{i}-c{j}', type=content_type,
                )
            CoursePrice.objects.create(
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course.id, title='Full', amount=Decimal('100'),
            )

    def count_queries(self, course_count):
        Course.objects.all().delete()
        self.make_courses(course_count)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(COURSE_LIST_URL, {'per_page': 50})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['data']), course_count)
        return len(ctx)

    def test_query_count_does_not_grow_with_the_number_of_courses(self):
        few = self.count_queries(2)
        many = self.count_queries(10)
        self.assertEqual(
            few,
            many,
            f'query count scales with page size: 2 courses -> {few}, '
            f'10 courses -> {many}. An N+1 has been reintroduced.',
        )

    def test_the_page_is_served_in_a_small_fixed_number_of_queries(self):
        self.assertLessEqual(self.count_queries(10), 15)


class HasOrderWiringTests(APITestCase):
    """`has_order` is a billing fact served on a courses payload.

    Courses must not import the app that owns orders, so billing fills a
    provider hook at startup. If that wiring ever breaks the field degrades
    silently to False -- which no other test would notice, because False is
    the correct answer for most rows.
    """

    def setUp(self):
        self.student = User.objects.create_user(
            phone='01810600001', name='Student', password='Str0ngPass!23'
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        self.bought = Course.objects.create(title='Bought', slug='bought')
        self.browsed = Course.objects.create(title='Browsed', slug='browsed')

        from apps.shop.models import Order

        Order.objects.create(
            user=self.student, course=self.bought,
            amount=Decimal('100'), total=Decimal('100'),
        )

    def test_the_provider_is_wired_at_startup(self):
        from apps.courses import selectors

        self.assertIsNotNone(
            selectors.ordered_course_ids_provider,
            'billing did not register its provider; has_order is now always False',
        )

    def test_has_order_reflects_a_real_order(self):
        body = self.client.get(COURSE_LIST_URL, {'per_page': 50}, **self.auth).json()
        flags = {row['slug']: row['has_order'] for row in body['data']}
        self.assertTrue(flags['bought'])
        self.assertFalse(flags['browsed'])

    def test_has_order_is_false_for_anonymous_callers(self):
        body = self.client.get(COURSE_LIST_URL, {'per_page': 50}).json()
        self.assertFalse(any(row['has_order'] for row in body['data']))


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
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(CourseUser.objects.filter(course=self.course, user=self.student).exists())

    def test_attach_by_numeric_id(self):
        response = self.client.post(
            ENROLLMENT_URL, {'slugOrId': str(self.course.pk), 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_attaching_with_a_price_sets_validity_and_payment_type(self):
        self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json', **self.auth,
        )
        enrolment = CourseUser.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrolment.payment_type, CourseUser.PaymentType.PAID)
        self.assertIsNotNone(enrolment.valid_till)

    def test_a_price_from_another_course_is_rejected(self):
        other = Course.objects.create(title='Other', slug='other')
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': other.slug, 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_attaching_an_unknown_user_is_a_validation_error(self):
        # The FK constraint used to surface this as an IntegrityError 500.
        response = self.client.post(
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': 999999},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn('user_id', response.json()['errors'])

    def test_attach_requires_a_valid_course_and_user(self):
        response = self.client.post(
            ENROLLMENT_URL, {'slugOrId': 'ghost', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_update_changes_payment_type(self):
        CourseUser.objects.create(course=self.course, user=self.student)
        response = self.client.patch(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'payment_type': 'paid'},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            CourseUser.objects.get(course=self.course, user=self.student).payment_type, 'paid'
        )

    def test_update_on_a_missing_enrolment_is_404(self):
        response = self.client.patch(
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def test_remove_deletes_the_enrolment(self):
        CourseUser.objects.create(course=self.course, user=self.student)
        response = self.client.delete(
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertTrue(response.json()['ok'])
        self.assertFalse(CourseUser.objects.exists())

    def test_remove_reports_false_when_nothing_matched(self):
        response = self.client.delete(
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json', **self.auth,
        )
        self.assertFalse(response.json()['ok'])

    def test_students_cannot_attach(self):
        student_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        response = self.client.post(
            ENROLLMENT_URL, {'slugOrId': 'ict', 'user_id': self.student.pk},
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
