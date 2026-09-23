"""Contract tests for the course catalogue, content gating and enrolment."""

from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.courses.models import (
    Content,
    ContentCompletion,
    Course,
    CourseCategory,
    CourseMaterial,
    CoursePrice,
    Enrollment,
    Section,
)
from apps.courses.services import import_enrollments
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

COURSE_LIST_URL = reverse('api:courses:course_list')
CATEGORY_LIST_URL = reverse('api:courses:course_category_list')
MY_COURSE_URL = reverse('api:courses:my_course_list')
ENROLLMENT_URL = reverse('api:courses:admin_enrollment')


class CatalogueTests(APITestCase):
    def setUp(self):
        self.category = CourseCategory.objects.create(title='HSC', slug='hsc')
        self.course = Course.objects.create(title='ICT Full', slug='ict-full', active=True, is_online=True)
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
        url = reverse('api:courses:course_detail', args=['ict-full'])
        self.assertEqual(self.client.get(url).json()['title'], 'ICT Full')

    def test_inactive_course_detail_is_404(self):
        url = reverse('api:courses:course_detail', args=['archived'])
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
            section = Section.objects.create(course=course, title='Ch1', slug=f'course-{i}-ch1')
            for j, content_type in enumerate([Content.Type.VIDEO, Content.Type.EXAM, Content.Type.NOTE]):
                Content.objects.create(
                    course=course,
                    section=section,
                    title=f'C{j}',
                    slug=f'course-{i}-c{j}',
                    type=content_type,
                )
            CoursePrice.objects.create(
                priceable_type=CoursePrice.PRICEABLE_COURSE,
                priceable_id=course.id,
                title='Full',
                amount=Decimal('100'),
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
        self.student = User.objects.create_user(phone='01810600001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.bought = Course.objects.create(title='Bought', slug='bought')
        self.browsed = Course.objects.create(title='Browsed', slug='browsed')

        from apps.billing.models import Order

        Order.objects.create(
            user=self.student,
            course=self.bought,
            amount=Decimal('100'),
            total=Decimal('100'),
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
        self.student = User.objects.create_user(phone='01810300001', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.course = Course.objects.create(title='ICT', slug='ict')
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


class MyCoursesTests(APITestCase):
    def setUp(self):
        self.student = User.objects.create_user(phone='01810300002', name='Student', password='Str0ngPass!23')
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.enrolled = Course.objects.create(title='Mine', slug='mine')
        Course.objects.create(title='Theirs', slug='theirs')
        Enrollment.objects.create(course=self.enrolled, user=self.student)

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get(MY_COURSE_URL).status_code, 401)

    def test_only_enrolled_courses_are_returned(self):
        body = self.client.get(MY_COURSE_URL, **self.auth).json()
        self.assertEqual([c['title'] for c in body['data']], ['Mine'])


class AdminEnrolmentTests(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone='01710300001',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.student = User.objects.create_user(phone='01810300003', name='Student', password='Str0ngPass!23')
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
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(Enrollment.objects.filter(course=self.course, user=self.student).exists())

    def test_attach_by_numeric_id(self):
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': str(self.course.pk), 'user_id': self.student.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)

    def test_attaching_with_a_price_sets_validity_and_payment_type(self):
        self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        enrolment = Enrollment.objects.get(course=self.course, user=self.student)
        self.assertEqual(enrolment.payment_type, Enrollment.PaymentType.PAID)
        self.assertIsNotNone(enrolment.valid_till)

    def test_a_price_from_another_course_is_rejected(self):
        other = Course.objects.create(title='Other', slug='other')
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': other.slug, 'user_id': self.student.pk, 'price_id': self.price.pk},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)

    def test_attaching_an_unknown_user_is_a_validation_error(self):
        # The FK constraint used to surface this as an IntegrityError 500.
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
        student_auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        response = self.client.post(
            ENROLLMENT_URL,
            {'slugOrId': 'ict', 'user_id': self.student.pk},
            format='json',
            **student_auth,
        )
        self.assertEqual(response.status_code, 403)


class AdminContentToggleTests(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone='01710300002',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        course = Course.objects.create(title='ICT', slug='ict')
        section = Section.objects.create(course=course, title='Ch1', slug='ict-ch1')
        self.content = Content.objects.create(
            course=course,
            section=section,
            title='Lesson',
            slug='ict-lesson',
            type=Content.Type.VIDEO,
            active=True,
            paid=True,
        )

    def url(self):
        return reverse('api:courses:admin_content_toggle', args=[self.content.pk])

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


class CourseMaterialListTests(APITestCase):
    """Supplementary files were admin-only, so a lecture sheet uploaded
    against a course reached nobody. Gated on the same enrolment rule the
    lessons use, expiry included."""

    def setUp(self):
        self.student = User.objects.create_user(
            phone='01710400001',
            name='Student',
            password='Str0ngPass!23',
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.course = Course.objects.create(title='ICT', slug='ict-materials', active=True)
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


class CourseProgressTests(APITestCase):
    """There was no progress model at all, so the player could only remember
    the last lesson opened, per device, in the browser's own storage."""

    def setUp(self):
        self.student = User.objects.create_user(
            phone='01710500001',
            name='Student',
            password='Str0ngPass!23',
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'}
        self.course = Course.objects.create(title='ICT', slug='ict-progress', active=True)
        section = Section.objects.create(course=self.course, title='Ch1', slug='ict-progress-ch1')
        self.lessons = [
            Content.objects.create(
                course=self.course,
                section=section,
                title=f'Lesson {i}',
                slug=f'ict-progress-l{i}',
                type=Content.Type.VIDEO,
                active=True,
            )
            for i in range(4)
        ]

    def url(self, slug=None):
        return reverse('api:courses:course_progress', args=[slug or self.course.slug])

    def enrol(self, **kwargs):
        return Enrollment.objects.create(course=self.course, user=self.student, **kwargs)

    def test_an_anonymous_visitor_is_rejected(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def test_a_student_without_an_enrolment_is_rejected(self):
        self.assertEqual(self.client.get(self.url(), **self.auth).status_code, 403)

    def test_an_expired_enrolment_is_rejected(self):
        self.enrol(valid_till=timezone.now() - timezone.timedelta(days=1))
        self.assertEqual(self.client.get(self.url(), **self.auth).status_code, 403)

    def test_a_fresh_enrolment_starts_at_zero(self):
        self.enrol()
        data = self.client.get(self.url(), **self.auth).data['data']
        self.assertEqual((data['completed'], data['total'], data['percent']), (0, 4, 0))

    def test_marking_a_lesson_advances_the_count(self):
        self.enrol()
        response = self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['completed'], 1)
        self.assertEqual(response.data['data']['percent'], 25)
        self.assertIn(self.lessons[0].pk, response.data['data']['completed_content_ids'])

    def test_marking_the_same_lesson_twice_counts_once(self):
        self.enrol()
        for _ in range(2):
            response = self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.data['data']['completed'], 1)

    def test_a_lesson_can_be_un_marked(self):
        self.enrol()
        self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        response = self.client.delete(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.data['data']['completed'], 0)

    def test_a_lesson_from_another_course_is_rejected(self):
        self.enrol()
        other = Course.objects.create(title='Other', slug='other-progress')
        other_section = Section.objects.create(course=other, title='Ch1', slug='other-progress-ch1')
        stranger = Content.objects.create(
            course=other,
            section=other_section,
            title='Nope',
            slug='other-progress-l0',
            type=Content.Type.VIDEO,
            active=True,
        )
        response = self.client.post(self.url(), {'content_id': stranger.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_adding_a_lesson_dilutes_the_percentage(self):
        """A course that gains content should not leave everyone at 100%."""
        self.enrol()
        for lesson in self.lessons:
            self.client.post(self.url(), {'content_id': lesson.pk}, format='json', **self.auth)
        self.assertEqual(self.client.get(self.url(), **self.auth).data['data']['percent'], 100)

        section = Section.objects.get(course=self.course)
        Content.objects.create(
            course=self.course,
            section=section,
            title='Lesson 5',
            slug='ict-progress-l5',
            type=Content.Type.VIDEO,
            active=True,
        )
        data = self.client.get(self.url(), **self.auth).data['data']
        self.assertEqual((data['completed'], data['total'], data['percent']), (4, 5, 80))


class ContentCompletionRealignmentTests(APITestCase):
    """A lesson that changes course must take its completions with it.

    `ContentCompletion` stores `course` next to `content` so progress can be
    counted without walking the section tree, and `save()` keeps the two in
    step. That guard only runs when the completion is saved, so before
    `apps/courses/signals.py` existed, moving a lesson silently left every
    completion crediting the course it had left.
    """

    def setUp(self):
        self.student = User.objects.create_user(phone='01810910001', name='Student')
        self.origin = Course.objects.create(title='Origin', slug='origin', active=True)
        self.destination = Course.objects.create(title='Destination', slug='destination', active=True)
        self.content = Content.objects.create(
            course=self.origin,
            section=Section.objects.create(course=self.origin, title='S1'),
            title='Lesson',
            active=True,
        )
        self.completion = ContentCompletion.objects.create(user=self.student, content=self.content, course=self.origin)

    def move_content(self):
        self.content.course = self.destination
        self.content.section = Section.objects.create(course=self.destination, title='S2')
        self.content.save()

    def test_moving_a_lesson_repoints_its_completions(self):
        self.move_content()
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.course_id, self.destination.pk)

    def test_progress_follows_the_lesson_to_its_new_course(self):
        """The reason this matters: progress is counted by course."""
        from apps.courses.selectors import course_progress

        self.move_content()
        self.assertEqual(course_progress(user=self.student, course=self.destination)['completed'], 1)
        self.assertEqual(course_progress(user=self.student, course=self.origin)['completed'], 0)

    def test_saving_a_lesson_that_did_not_move_changes_nothing(self):
        self.content.title = 'Renamed'
        self.content.save()
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.course_id, self.origin.pk)

    def test_other_lessons_completions_are_untouched(self):
        other = Content.objects.create(
            course=self.origin,
            section=self.content.section_id and self.content.section,
            title='Another',
            active=True,
        )
        other_completion = ContentCompletion.objects.create(user=self.student, content=other, course=self.origin)
        self.move_content()
        other_completion.refresh_from_db()
        self.assertEqual(other_completion.course_id, self.origin.pk)


class ImportEnrollmentsPhoneTests(APITestCase):
    """A sheet may spell a number any of the ways `core.phones` accepts;
    stored numbers are canonical, so the lookup has to normalise first."""

    def setUp(self):
        self.course = Course.objects.create(title='Phones', slug='phones-course')
        self.student = User.objects.create_user(phone='01810001111', name='Student')

    def test_a_country_code_sheet_still_enrols(self):
        result = import_enrollments(
            course=self.course,
            records=[{'phone': '+8801810001111'}, {'phone': '018-1000-1111'}],
        )
        self.assertEqual(result['attached'], 2)
        self.assertEqual(result['missing'], 0)
        self.assertTrue(Enrollment.objects.filter(course=self.course, user=self.student).exists())

    def test_an_unknown_number_is_still_counted_missing(self):
        result = import_enrollments(course=self.course, records=[{'phone': '+8801999999999'}])
        self.assertEqual(result, {'attached': 0, 'missing': 1})

    def test_a_blank_phone_is_counted_missing(self):
        result = import_enrollments(course=self.course, records=[{'phone': ''}, {'phone': 'n/a'}])
        self.assertEqual(result, {'attached': 0, 'missing': 2})


class CourseTeacherTests(APITestCase):
    """Assigning a teacher to a course."""

    def setUp(self):
        admin = User.objects.create_user(
            phone='01700001111', name='Admin', password='Str0ngPass!23', role=User.Role.ADMIN
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='ICT Full', slug='ict-full')
        self.other = Course.objects.create(title='Other', slug='other')

        self.teacher = User.objects.create_user(phone='01710001111', name='Rahad Sir', role=User.Role.TEACHER)
        TeacherProfile.objects.create(user=self.teacher, designation='Founder')
        self.url = reverse('api:courses:admin-course-teacher-list')

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
        student = User.objects.create_user(phone='01810002222', name='Student')

        response = self.client.post(
            self.url,
            {'course_id': self.course.pk, 'user_id': student.pk},
            format='json',
            **self.auth,
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn('user_id', response.json()['errors'])
