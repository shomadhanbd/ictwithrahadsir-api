from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.academic.models import Batch, ClassLevel, Group
from apps.billing.models import Product
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import (
    Content,
    Course,
    CourseTeacher,
    Enrollment,
    Section,
)
from apps.identity.models import User
from apps.profiles.models import StudentProfile

COURSE_LIST_URL = reverse('api:courses:course_list')
MY_COURSE_URL = reverse('api:courses:my_course_list')


class CatalogueTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(title='ICT Full', slug='ict-full', status='published', is_online=True)
        Course.objects.create(title='Archived', slug='archived', status='archived')
        Course.objects.create(title='Offline', slug='offline', status='published', is_online=False)

    def test_only_active_courses_are_listed(self):
        titles = [c['title'] for c in self.client.get(COURSE_LIST_URL).json()['data']]
        self.assertNotIn('Archived', titles)
        self.assertEqual(len(titles), 2)

    def test_courses_filter_by_online_flag(self):
        body = self.client.get(COURSE_LIST_URL, {'is_online': 'true'}).json()
        self.assertEqual([c['title'] for c in body['data']], ['ICT Full'])

    def test_course_detail_is_fetched_by_slug(self):
        url = reverse('api:courses:course_detail', args=['ict-full'])
        self.assertEqual(self.client.get(url).json()['title'], 'ICT Full')

    def test_inactive_course_detail_is_404(self):
        url = reverse('api:courses:course_detail', args=['archived'])
        self.assertEqual(self.client.get(url).status_code, 404)


class CourseStatusTests(APITestCase):
    """Drafts are staff-only, published courses are listed, archived ones still serve their students."""

    def setUp(self):
        self.draft = Course.objects.create(title='Draft', slug='draft')
        self.live = Course.objects.create(title='Live', slug='live', status='published')
        self.old = Course.objects.create(title='Old', slug='old', status='archived')
        self.student = make_user()
        self.auth = bearer(self.student)

    def detail(self, slug, **auth):
        return self.client.get(reverse('api:courses:course_detail', args=[slug]), **auth)

    def test_only_published_courses_are_listed(self):
        slugs = [c['slug'] for c in self.client.get(COURSE_LIST_URL).json()['data']]
        self.assertEqual(slugs, ['live'])

    def test_draft_and_archived_details_are_hidden_from_visitors(self):
        self.assertEqual(self.detail('draft').status_code, 404)
        self.assertEqual(self.detail('old').status_code, 404)
        self.assertEqual(self.detail('draft', **self.auth).status_code, 404)

    def test_a_drafts_own_teacher_can_preview_it(self):
        teacher = make_user(role=User.Role.TEACHER)
        CourseTeacher.objects.create(course=self.draft, user=teacher)
        response = self.detail('draft', **bearer(teacher))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'draft')

    def test_another_teacher_cannot_preview_a_draft(self):
        """Unpublished curricula stay with their own teachers."""
        self.assertEqual(self.detail('draft', **bearer(make_user(role=User.Role.TEACHER))).status_code, 404)
        self.assertEqual(self.detail('draft', **bearer(make_user(role=User.Role.ADMIN))).status_code, 200)

    def test_archived_course_still_serves_its_enrolled_students(self):
        Enrollment.objects.create(course=self.old, user=self.student)
        self.assertEqual(self.detail('old', **self.auth).status_code, 200)
        mine = [c['slug'] for c in self.client.get(MY_COURSE_URL, **self.auth).json()['data']]
        self.assertEqual(mine, ['old'])
        progress = self.client.get(reverse('api:courses:course_progress', args=['old']), **self.auth)
        self.assertEqual(progress.status_code, 200)
        materials = self.client.get(reverse('api:courses:course_material_list', args=['old']), **self.auth)
        self.assertEqual(materials.status_code, 200)

    def test_an_enrolment_does_not_open_a_draft(self):
        Enrollment.objects.create(course=self.draft, user=self.student)
        self.assertEqual(self.detail('draft', **self.auth).status_code, 404)

    def test_published_at_is_stamped_once(self):
        self.assertIsNone(self.draft.published_at)
        self.draft.status = 'published'
        self.draft.save()
        first = self.draft.published_at
        self.assertIsNotNone(first)

        self.draft.status = 'archived'
        self.draft.save()
        self.draft.status = 'published'
        self.draft.save()
        self.assertEqual(self.draft.published_at, first)


class CourseAudienceTests(APITestCase):
    """A targeted course is listed only to students of its level and group; batch only filters."""

    def setUp(self):
        self.hsc = ClassLevel.objects.create(name='HSC', slug='hsc')
        self.ssc = ClassLevel.objects.create(name='SSC', slug='ssc')
        self.science = Group.objects.create(name='Science', slug='science')
        self.arts = Group.objects.create(name='Arts', slug='arts')
        self.hsc_2027 = Batch.objects.create(slug=next_slug("batch"), name='HSC-2027', class_level=self.hsc)

        Course.objects.create(status='published', title='Open', slug='open')
        Course.objects.create(
            status='published', title='HSC all', slug='hsc-all', class_level=self.hsc, batch=self.hsc_2027
        )
        Course.objects.create(
            status='published', title='HSC science', slug='hsc-science', class_level=self.hsc, group=self.science
        )
        self.hsc_arts = Course.objects.create(
            status='published', title='HSC arts', slug='hsc-arts', class_level=self.hsc, group=self.arts
        )
        Course.objects.create(status='published', title='SSC', slug='ssc', class_level=self.ssc)

        self.student = make_user()
        StudentProfile.objects.update_or_create(
            user=self.student, defaults={'class_level': self.hsc, 'group': self.science}
        )
        self.auth = bearer(self.student)

    def titles(self, params=None, **auth):
        return sorted(c['title'] for c in self.client.get(COURSE_LIST_URL, params or {}, **auth).json()['data'])

    def test_student_sees_open_and_matching_courses(self):
        self.assertEqual(self.titles(**self.auth), ['HSC all', 'HSC science', 'Open'])

    def test_visitor_sees_everything(self):
        self.assertEqual(len(self.titles()), 5)

    def test_teacher_sees_everything(self):
        teacher = make_user(role=User.Role.TEACHER)
        auth = bearer(teacher)
        self.assertEqual(len(self.titles(**auth)), 5)

    def test_student_without_class_level_sees_everything(self):
        StudentProfile.objects.filter(user=self.student).update(class_level=None, group=None)
        self.assertEqual(len(self.titles(**self.auth)), 5)

    def test_student_without_group_sees_only_level_wide_courses(self):
        StudentProfile.objects.filter(user=self.student).update(group=None)
        self.assertEqual(self.titles(**self.auth), ['HSC all', 'Open'])

    def test_filters_by_batch_level_and_group(self):
        self.assertEqual(self.titles({'batch': self.hsc_2027.slug}), ['HSC all'])
        self.assertEqual(self.titles({'class_level': 'ssc'}), ['SSC'])
        self.assertEqual(self.titles({'group': 'arts'}), ['HSC arts'])

    def test_filter_cannot_reveal_a_hidden_course(self):
        self.assertEqual(self.titles({'group': 'arts'}, **self.auth), [])

    def test_payload_carries_the_audience(self):
        course = next(c for c in self.client.get(COURSE_LIST_URL).json()['data'] if c['slug'] == 'hsc-all')
        self.assertEqual(course['class_level'], {'id': self.hsc.id, 'name': 'HSC', 'slug': 'hsc'})
        self.assertIsNone(course['group'])
        self.assertEqual(course['batch']['slug'], self.hsc_2027.slug)

    def test_hidden_course_detail_is_404_unless_enrolled(self):
        url = reverse('api:courses:course_detail', args=['hsc-arts'])
        self.assertEqual(self.client.get(url, **self.auth).status_code, 404)

        Enrollment.objects.create(course=self.hsc_arts, user=self.student)
        self.assertEqual(self.client.get(url, **self.auth).status_code, 200)
        my = [c['slug'] for c in self.client.get(MY_COURSE_URL, **self.auth).json()['data']]
        self.assertIn('hsc-arts', my)

    def test_homepage_featured_courses_respect_audience(self):
        Course.objects.update(is_featured=True)
        body = self.client.get(reverse('api:content:home'), **self.auth).json()
        self.assertEqual(sorted(c['title'] for c in body['courses']), ['HSC all', 'HSC science', 'Open'])


class PublicAcademicListTests(APITestCase):
    def test_lists_active_batches_for_a_level(self):
        hsc = ClassLevel.objects.create(name='HSC', slug='hsc')
        ssc = ClassLevel.objects.create(name='SSC', slug='ssc')
        Batch.objects.create(slug=next_slug("batch"), name='HSC-2027', class_level=hsc)
        Batch.objects.create(slug=next_slug("batch"), name='HSC-2020', class_level=hsc, is_active=False)
        Batch.objects.create(slug=next_slug("batch"), name='SSC-2027', class_level=ssc)
        body = self.client.get(reverse('api:academic:batch_list'), {'class_level': 'hsc'}).json()
        self.assertEqual([b['name'] for b in body['data']], ['HSC-2027'])
        self.assertEqual(body['data'][0]['class_level'], 'hsc')


class CourseProfilePayloadTests(APITestCase):
    def setUp(self):
        self.course = Course.objects.create(
            title='Physics',
            slug='physics',
            status='published',
            summary='All of HSC physics.',
            thumbnail='https://cdn.example.com/thumb.png',
            fake_student_count=100,
            enrollment_deadline=timezone.now() - timezone.timedelta(days=1),
            faqs=[{'question': 'Recorded?', 'answer': 'Yes.'}],
        )
        student = make_user()
        Enrollment.objects.create(course=self.course, user=student)

    def test_student_count_adds_the_padding_and_hides_it(self):
        card = self.client.get(COURSE_LIST_URL).json()['data'][0]
        self.assertEqual(card['student_count'], 101)
        self.assertNotIn('fake_student_count', card)

    def test_enrollment_closes_after_the_deadline(self):
        card = self.client.get(COURSE_LIST_URL).json()['data'][0]
        self.assertFalse(card['enrollment_open'])

    def test_detail_carries_the_landing_page(self):
        body = self.client.get(reverse('api:courses:course_detail', args=['physics'])).json()
        self.assertEqual(body['faqs'], [{'question': 'Recorded?', 'answer': 'Yes.'}])
        # Blank SEO fields fall back to the course's own copy.
        self.assertEqual(
            body['seo'],
            {'title': 'Physics', 'description': 'All of HSC physics.', 'image': 'https://cdn.example.com/thumb.png'},
        )

    def test_filters_by_delivery_difficulty_and_language(self):
        Course.objects.create(
            slug=next_slug("course"),
            title='Live English',
            status='published',
            delivery='live',
            difficulty='advanced',
            language='en',
        )
        for params in ({'delivery': 'live'}, {'difficulty': 'advanced'}, {'language': 'en'}):
            titles = [c['title'] for c in self.client.get(COURSE_LIST_URL, params).json()['data']]
            self.assertEqual(titles, ['Live English'], params)


class CourseListQueryCountTests(APITestCase):
    """The catalogue's query count does not grow with the number of courses."""

    def make_courses(self, count):
        for i in range(count):
            course = Course.objects.create(status='published', title=f'Course {i}', slug=f'course-{i}')
            section = Section.objects.create(course=course, title='Ch1', slug=f'course-{i}-ch1')
            for j, content_type in enumerate([Content.Type.VIDEO, Content.Type.EXAM, Content.Type.NOTE]):
                Content.objects.create(
                    course=course,
                    section=section,
                    title=f'C{j}',
                    slug=f'course-{i}-c{j}',
                    type=content_type,
                )
            package = Product.objects.create(
                product_id=next_slug("product"), title=f'Package {i}', price=100, base_price=100
            )
            package.courses.add(course)

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
    """`has_purchased` comes from billing through a provider hook filled at startup."""

    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.bought = Course.objects.create(status='published', title='Bought', slug='bought')
        self.browsed = Course.objects.create(status='published', title='Browsed', slug='browsed')

        from apps.billing.models import Payment, Product

        product = Product.objects.create(product_id=next_slug("product"), title='Bundle', price=100, base_price=100)
        product.courses.add(self.bought)
        Payment.objects.create(user=self.student, product=product, amount=100, status=Payment.Status.VALID)

    def test_the_provider_is_wired_at_startup(self):
        from apps.core import providers

        self.assertIsNotNone(
            providers.get('courses.ordered_course_ids'),
            'billing did not register its provider; has_purchased is now always False',
        )

    def test_has_purchased_reflects_a_real_order(self):
        body = self.client.get(COURSE_LIST_URL, {'per_page': 50}, **self.auth).json()
        flags = {row['slug']: row['has_purchased'] for row in body['data']}
        self.assertTrue(flags['bought'])
        self.assertFalse(flags['browsed'])

    def test_has_purchased_is_false_for_anonymous_callers(self):
        body = self.client.get(COURSE_LIST_URL, {'per_page': 50}).json()
        self.assertFalse(any(row['has_purchased'] for row in body['data']))


class MyCoursesTests(APITestCase):
    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.enrolled = Course.objects.create(status='published', title='Mine', slug='mine')
        Course.objects.create(status='published', title='Theirs', slug='theirs')
        Enrollment.objects.create(course=self.enrolled, user=self.student)

    def test_authentication_is_required(self):
        self.assertEqual(self.client.get(MY_COURSE_URL).status_code, 401)

    def test_only_enrolled_courses_are_returned(self):
        body = self.client.get(MY_COURSE_URL, **self.auth).json()
        self.assertEqual([c['title'] for c in body['data']], ['Mine'])
