"""Golden response-shape tests for the app re-decomposition.

`UrlContractTests` guards which *paths* are served. It says nothing about
what comes back from them, so it stays green while a serializer rewrite
silently changes the shape of a payload behind an unchanged URL. The app
re-decomposition does exactly that: extracting `Exam` off `Content` and
unifying the teacher models both rewrite serializer internals under
paths that must not move.

These assert exact key lists and the literal values that come from model
field defaults, so a shape change fails loudly. They live in `core`
because `core` survives the restructure with its name intact.

Key order matters: DRF emits keys in `Meta.fields` order, and the two
frontends destructure these payloads.
"""

from django.test import TestCase
from django.urls import reverse

from rest_framework.authtoken.models import Token

from apps.content.models import Advertisement, Page, Testimonial
from apps.courses.models import Content, Course, CourseCategory, CourseTeacher, Section
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

#: Exactly what `/api/public/home/` returns, in order.
HOME_KEYS = [
    'courses',
    'courseCategories',
    'advertisement',
    'testimonials',
    'counters',
    'suceesstorycounter',
    'instructors',
    'bannerImage',
]

#: Both the homepage `instructors` (profiles.TeacherProfile) and course-detail
#: `instructors` (courses.CourseTeacher) serialise to this same key list. The
#: key is spelled `instructors` and stays that way: it is the one piece of the
#: old vocabulary kept, because an unknown mobile client may read it.
#: Keeping it frozen is what proved the move out of `faculty` changed no
#: payload: widening it here would remove the guard, not satisfy it.
PUBLIC_TEACHER_KEYS = [
    'id',
    'name',
    'designation',
    'description',
    'type',
    'order',
    'image',
]

COURSE_LIST_KEYS = [
    'id',
    'title',
    'slug',
    'subtitle',
    'duration',
    'is_online',
    'active',
    'featured',
    'fake_user_count',
    'video_count',
    'class_count',
    'exam_count',
    'note_count',
    'link_count',
    'live_count',
    'audio_count',
    'online_count',
    'offline_count',
    'image',
    'price',
    'categories',
    'instructors',
    'routines',
    'subscription_status',
    'has_order',
    'users_count',
]

#: The original 13 keys in their original order. `teacher_id` is gone with the
#: roster model it pointed at -- an assignment names the account directly now
#: -- and everything but `commission` and `order` is read through that account,
#: so the panel's table renders unchanged while none of it is editable here.
ADMIN_COURSE_TEACHER_KEYS = [
    'id',
    'course_id',
    'user_id',
    'name',
    'email',
    'phone',
    'designation',
    'description',
    'institute',
    'type',
    'order',
    'commission',
    'image',
]


class ResponseShapeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='01710900001',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.admin).key}'}

        self.category = CourseCategory.objects.create(title='HSC', slug='hsc')
        self.course = Course.objects.create(
            title='ICT',
            slug='ict',
            active=True,
            featured=True,
            image='http://localhost:8000/media/seed/course-0.png',
        )
        self.course.categories.add(self.category)

        self.teacher_user = User.objects.create_user(
            phone='01899000111',
            name='Rahad Sir',
            role=User.Role.TEACHER,
            image='http://localhost:8000/media/seed/teacher-0.png',
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            designation='Founder',
            description='Bio',
        )
        CourseTeacher.objects.create(course=self.course, user=self.teacher_user)

        Testimonial.objects.create(name='Student', description='Great', ratings=5)
        Advertisement.objects.create(title='Admission open')
        Page.objects.update_or_create(
            key='homeBannerImage',
            defaults={'slug': 'homeBannerImage', 'value_type': Page.ValueType.IMAGE},
        )

        self.section = Section.objects.create(course=self.course, title='Ch1', slug='ict-ch1')
        self.exam_content = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Exam',
            slug='ict-exam',
            type=Content.Type.EXAM,
        )
        self.video_content = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Video',
            slug='ict-video',
            type=Content.Type.VIDEO,
        )

    # -- public ----------------------------------------------------------

    def test_home_payload_shape(self):
        body = self.client.get(reverse('api:content:home')).json()
        self.assertEqual(list(body.keys()), HOME_KEYS)
        self.assertEqual(list(body['instructors'][0].keys()), PUBLIC_TEACHER_KEYS)
        self.assertEqual(list(body['courses'][0].keys()), COURSE_LIST_KEYS)

    def test_home_instructors_are_the_teacher_roster(self):
        body = self.client.get(reverse('api:content:home')).json()
        self.assertEqual(body['instructors'][0]['name'], 'Rahad Sir')
        self.assertEqual(body['instructors'][0]['type'], 'permanent')
        self.assertEqual(
            body['instructors'][0]['image'],
            {'id': body['instructors'][0]['image']['id'], 'link': 'http://localhost:8000/media/seed/teacher-0.png'},
        )

    def test_course_list_payload_shape(self):
        body = self.client.get(reverse('api:courses:course_list')).json()
        self.assertEqual(list(body['data'][0].keys()), COURSE_LIST_KEYS)

    def test_course_detail_instructors_shape(self):
        url = reverse('api:courses:course_detail', args=[self.course.slug])
        body = self.client.get(url).json()

        instructor = body['instructors'][0]
        self.assertEqual(list(instructor.keys()), PUBLIC_TEACHER_KEYS)
        self.assertEqual(instructor['name'], 'Rahad Sir')
        # MediaField renders a {id, link} object, not a bare URL.
        self.assertEqual(sorted(instructor['image'].keys()), ['id', 'link'])
        self.assertEqual(
            instructor['image']['link'],
            'http://localhost:8000/media/seed/teacher-0.png',
        )

    # -- admin -----------------------------------------------------------

    def test_admin_course_teacher_payload_shape(self):
        body = self.client.get(reverse('api:courses:admin-course-teacher-list'), **self.auth)
        self.assertEqual(list(body.json()['data'][0].keys()), ADMIN_COURSE_TEACHER_KEYS)

    # -- exam taking -----------------------------------------------------


class AdminSearchTests(TestCase):
    """`?search=` must actually filter.

    The global SearchFilter is enabled for every view, but it is inert
    without `search_fields` on the view itself — so these endpoints accepted
    `?search=` and returned the unfiltered list. The admin panel ships a
    search box against each of them, which therefore did nothing at all.
    """

    def setUp(self):
        from apps.content.models import Notice

        admin = User.objects.create_user(phone='01899000111', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

        Notice.objects.create(title='Exam routine published')
        Notice.objects.create(title='Holiday announcement')
        Course.objects.create(title='Physics crash course')
        Course.objects.create(title='Chemistry masterclass')
        for i, (name, subject) in enumerate([('Rahim Uddin', 'Physics'), ('Karim Ahmed', 'Chemistry')]):
            TeacherProfile.objects.create(
                user=User.objects.create_user(phone=f'0188800{i:04d}', name=name, role=User.Role.TEACHER),
                designation=subject,
            )

    def assert_filters(self, path, term, expected):
        unfiltered = self.client.get(path, **self.auth).json()['meta']['total']
        filtered = self.client.get(path, {'search': term}, **self.auth).json()['meta']['total']
        self.assertEqual(filtered, expected)
        self.assertLess(filtered, unfiltered, f'{path} ignored ?search=')

    def test_notice_search_filters(self):
        self.assert_filters(reverse('api:content:admin-notice-list'), 'Holiday', 1)

    def test_course_search_filters(self):
        self.assert_filters(reverse('api:courses:admin-course-list'), 'Physics', 1)

    def test_teacher_search_filters(self):
        self.assert_filters(reverse('api:profiles:admin-teacher-list'), 'Rahim', 1)

    def test_search_that_matches_nothing_returns_nothing(self):
        """The panel's empty state depends on this actually being empty."""
        url = reverse('api:content:admin-notice-list')
        body = self.client.get(url, {'search': 'zzzznomatch'}, **self.auth).json()
        self.assertEqual(body['meta']['total'], 0)
        self.assertEqual(body['data'], [])


class SlugOrPkLookupTests(TestCase):
    """The admin panel routes on the numeric id; the site uses the slug.

    `AdminCourseViewSet.lookup_field` is `slug`, so `/admin/courses/6/` used
    to 404 -- it looked for a course whose slug was literally "6". The panel
    only ever has the id, so every course detail route was unreachable.
    """

    def setUp(self):
        admin = User.objects.create_user(phone='01899000222', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='Physics First Paper')

    def detail(self, value):
        return self.client.get(f'/api/private/courses/{value}/', **self.auth)

    def test_detail_by_pk(self):
        res = self.detail(self.course.pk)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], 'Physics First Paper')

    def test_detail_by_slug_still_works(self):
        res = self.detail(self.course.slug)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], 'Physics First Paper')

    def test_numeric_slug_is_still_reachable(self):
        # A pk lookup that misses falls through to the slug, or a course
        # titled "2026" would become unopenable.
        numeric = Course.objects.create(title='2026')
        self.assertTrue(numeric.slug.isdigit(), f'expected digits, got {numeric.slug!r}')
        self.assertFalse(Course.objects.filter(pk=numeric.slug).exists())
        res = self.detail(numeric.slug)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], '2026')

    def test_unknown_id_404s(self):
        self.assertEqual(self.detail(99999).status_code, 404)


class CourseTabSearchTests(TestCase):
    """The course tabs all ship a search box; each endpoint must honour it.

    Routines, teachers and the enrolled-student list had no
    `search_fields`, so `?search=` was accepted and ignored -- the same inert
    SearchFilter problem as the top-level admin lists.
    """

    def setUp(self):
        from apps.courses.models import CourseTeacher, Enrollment, Routine

        admin = User.objects.create_user(phone='01899000333', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='Search Tab Course')

        Routine.objects.create(course=self.course, title='September routine', link='a.pdf')
        Routine.objects.create(course=self.course, title='October routine', link='b.pdf')

        for i, name in enumerate(['Rahim Uddin', 'Karim Ahmed']):
            teacher = User.objects.create_user(
                phone=f'0189900{i:04d}',
                name=name,
                email=f'{name[0].lower()}@x.com',
                role=User.Role.TEACHER,
            )
            TeacherProfile.objects.create(user=teacher)
            CourseTeacher.objects.create(course=self.course, user=teacher)

        for i, name in enumerate(['Nusrat Jahan', 'Imran Hossain']):
            student = User.objects.create_user(phone=f'0180900{i:04d}', name=name, role=User.Role.STUDENT)
            Enrollment.objects.create(course=self.course, user=student)

    def assert_filters(self, path, term, expected):
        unfiltered = self.client.get(path, **self.auth).json()['meta']['total']
        filtered = self.client.get(path, {'search': term}, **self.auth).json()['meta']['total']
        self.assertEqual(filtered, expected, f'{path} ?search={term}')
        self.assertLess(filtered, unfiltered, f'{path} ignored ?search=')

    def test_routine_search_filters(self):
        self.assert_filters('/api/private/routines/', 'October', 1)

    def test_course_teacher_search_filters(self):
        self.assert_filters('/api/private/course-teachers/', 'Karim', 1)

    def test_enrolled_student_search_filters(self):
        self.assert_filters(f'/api/private/courses/{self.course.pk}/enrollments/', 'Nusrat', 1)

    def test_enrolment_pages_do_not_overlap(self):
        """An unordered queryset let a student land on two pages or none."""
        from apps.courses.models import Enrollment

        for i in range(2, 8):
            student = User.objects.create_user(phone=f'0180911{i:04d}', name=f'Student {i}', role=User.Role.STUDENT)
            Enrollment.objects.create(course=self.course, user=student)

        path = f'/api/private/courses/{self.course.pk}/enrollments/'
        seen = []
        for page in (1, 2, 3, 4):
            body = self.client.get(path, {'page': page, 'per_page': 2}, **self.auth).json()
            seen.extend(row['id'] for row in body['data'])

        self.assertEqual(len(seen), len(set(seen)), f'a student appeared twice: {seen}')
        self.assertEqual(len(seen), Enrollment.objects.filter(course=self.course).count())


class CategorySearchTests(TestCase):
    """The categories screen searches on the server, at either level."""

    def setUp(self):
        from apps.courses.models import CourseCategory

        admin = User.objects.create_user(phone='01899000444', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.parent = CourseCategory.objects.create(title='HSC ICT')
        CourseCategory.objects.create(title='Admission Prep')
        CourseCategory.objects.create(title='HSC 2026', category=self.parent)
        CourseCategory.objects.create(title='HSC 2027', category=self.parent)

    def test_root_search_filters(self):
        path = '/api/private/course-categories/'
        unfiltered = self.client.get(path, **self.auth).json()['meta']['total']
        filtered = self.client.get(path, {'search': 'Admission'}, **self.auth).json()
        self.assertEqual(filtered['meta']['total'], 1)
        self.assertLess(filtered['meta']['total'], unfiltered)

    def test_subcategory_search_stays_within_the_parent(self):
        # The filter and the search have to compose, or searching inside a
        # category would surface siblings from elsewhere in the tree.
        body = self.client.get(
            '/api/private/course-categories/',
            {'category_id': self.parent.pk, 'search': '2027'},
            **self.auth,
        ).json()
        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['title'], 'HSC 2027')

    def test_detail_by_pk_for_the_parent_heading(self):
        res = self.client.get(f'/api/private/course-categories/{self.parent.pk}/', **self.auth)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], 'HSC ICT')


class CourseMaterialCrudTests(TestCase):
    """Materials were list-only, so the admin screen was a dead end.

    The endpoint is a full viewset now; these pin the write paths and the
    search that the screen's box depends on.
    """

    def setUp(self):
        admin = User.objects.create_user(phone='01899000666', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        self.course = Course.objects.create(title='Material Host Course')

    def test_create_update_delete(self):
        from apps.courses.models import CourseMaterial

        created = self.client.post(
            '/api/private/course-materials/',
            {'title': 'Lecture sheet 1', 'type': 'pdf', 'course_id': self.course.pk},
            content_type='application/json',
            **self.auth,
        )
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.json()['id']

        renamed = self.client.patch(
            f'/api/private/course-materials/{pk}/',
            {'title': 'Lecture sheet 2'},
            content_type='application/json',
            **self.auth,
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()['title'], 'Lecture sheet 2')

        gone = self.client.delete(f'/api/private/course-materials/{pk}/', **self.auth)
        self.assertEqual(gone.status_code, 204)
        self.assertFalse(CourseMaterial.objects.filter(pk=pk).exists())

    def test_list_is_paginated_and_searchable(self):
        from apps.courses.models import CourseMaterial

        CourseMaterial.objects.create(title='Algebra notes', course=self.course)
        CourseMaterial.objects.create(title='Geometry notes', course=self.course)

        body = self.client.get('/api/private/course-materials/', **self.auth).json()
        self.assertIn('meta', body, 'the screen paginates; the list must carry meta')
        self.assertEqual(body['meta']['total'], 2)

        filtered = self.client.get('/api/private/course-materials/', {'search': 'Algebra'}, **self.auth).json()
        self.assertEqual(filtered['meta']['total'], 1)

    def test_filter_by_course(self):
        from apps.courses.models import CourseMaterial

        other = Course.objects.create(title='Another Course')
        CourseMaterial.objects.create(title='Mine', course=self.course)
        CourseMaterial.objects.create(title='Theirs', course=other)

        body = self.client.get('/api/private/course-materials/', {'course_id': self.course.pk}, **self.auth).json()
        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['title'], 'Mine')


class AdminPaymentListTests(TestCase):
    """The payments screen searches and filters on the server.

    Neither worked: the view had no `search_fields`, so `?search=` was
    accepted and ignored, and there was no status filter at all — which is
    what the screen mainly exists to do.
    """

    def setUp(self):
        from apps.billing.models import Order, Payment

        admin = User.objects.create_user(phone='01899000777', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}
        course = Course.objects.create(title='Paid Course')

        for name, phone, txn, status in [
            ('Nusrat Jahan', '01810500001', 'TRX-AAA-111', Payment.Status.PENDING),
            ('Imran Hossain', '01810500002', 'TRX-BBB-222', Payment.Status.SUCCESSFUL),
            ('Rahim Uddin', '01810500003', 'TRX-CCC-333', Payment.Status.FAILED),
        ]:
            user = User.objects.create_user(phone=phone, name=name, role=User.Role.STUDENT)
            order = Order.objects.create(user=user, course=course, amount=500, total=500)
            Payment.objects.create(order=order, amount=500, transaction_id=txn, status=status)

    def get(self, **params):
        return self.client.get('/api/private/payments/', params, **self.auth).json()

    def test_search_by_payer_name(self):
        body = self.get(search='Nusrat')
        self.assertEqual(body['meta']['total'], 1)

    def test_search_by_transaction_id(self):
        body = self.get(search='BBB')
        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['transaction_id'], 'TRX-BBB-222')

    def test_search_by_phone(self):
        self.assertEqual(self.get(search='01810500003')['meta']['total'], 1)

    def test_status_filter(self):
        self.assertEqual(self.get(status='pending')['meta']['total'], 1)
        self.assertEqual(self.get(status='successful')['meta']['total'], 1)
        self.assertEqual(self.get(status='all')['meta']['total'], 3)
        self.assertEqual(self.get()['meta']['total'], 3)

    def test_pages_do_not_overlap(self):
        seen = []
        for page in (1, 2, 3):
            seen.extend(r['id'] for r in self.get(page=page, per_page=1)['data'])
        self.assertEqual(len(seen), len(set(seen)), f'a payment appeared twice: {seen}')
        self.assertEqual(len(seen), 3)


class ContentSearchTests(TestCase):
    """Every content screen ships a search box; none of the endpoints had
    `search_fields`, so all of them accepted `?search=` and ignored it."""

    def setUp(self):
        from apps.content.models import EBook, NoticeCategory

        admin = User.objects.create_user(phone='01899000888', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

        NoticeCategory.objects.create(title='Exam schedule')
        NoticeCategory.objects.create(title='Holiday notice')
        Testimonial.objects.create(name='Nusrat Jahan', description='Great course')
        Testimonial.objects.create(name='Imran Hossain', description='Very helpful')
        Advertisement.objects.create(title='Admission banner', type='banner')
        Advertisement.objects.create(title='Seminar popup', type='popup')
        EBook.objects.create(title='ICT Complete Guide')
        EBook.objects.create(title='Physics Workbook')

    def assert_filters(self, path, term, expected):
        unfiltered = self.client.get(path, **self.auth).json()['meta']['total']
        filtered = self.client.get(path, {'search': term}, **self.auth).json()['meta']['total']
        self.assertEqual(filtered, expected, f'{path} ?search={term}')
        self.assertLess(filtered, unfiltered, f'{path} ignored ?search=')

    def test_notice_category_search(self):
        self.assert_filters('/api/private/notice-categories/', 'Holiday', 1)

    def test_testimonial_search(self):
        self.assert_filters('/api/private/testimonials/', 'Nusrat', 1)

    def test_advertisement_search(self):
        self.assert_filters('/api/private/advertisements/', 'popup', 1)

    def test_ebook_search(self):
        self.assert_filters('/api/private/ebooks/', 'Physics', 1)

    def test_pages_expose_value_type(self):
        """The screen picks the editor from this; it used to guess from the key."""
        # These keys are seeded by a migration, so upsert rather than create.
        Page.objects.update_or_create(key='about', defaults={'value_type': Page.ValueType.HTML, 'value': '<p>hi</p>'})
        Page.objects.update_or_create(
            key='homeStudentCounter',
            defaults={'value_type': Page.ValueType.COUNTER, 'value': '42'},
        )

        body = self.client.get('/api/private/pages/', **self.auth).json()
        by_key = {p['key']: p for p in body['data']}
        self.assertEqual(by_key['about']['value_type'], 'html')
        self.assertEqual(by_key['homeStudentCounter']['value_type'], 'counter')


class AdminContactListTests(TestCase):
    """The contacts inbox searches and filters on the server.

    Neither worked: no `search_fields`, no read filter, and no ordering — so
    an inbox could repeat or drop a message across pages.
    """

    def setUp(self):
        from apps.support.models import ContactMessage

        admin = User.objects.create_user(phone='01899000999', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'}

        ContactMessage.objects.create(
            name='Nusrat Jahan',
            phone='01810600001',
            subject='Refund query',
            message='How do I get a refund?',
            is_read=False,
        )
        ContactMessage.objects.create(
            name='Imran Hossain',
            phone='01810600002',
            subject='Course access',
            message='Cannot open the videos',
            is_read=True,
        )
        ContactMessage.objects.create(
            name='Rahim Uddin',
            phone='01810600003',
            subject='Batch timing',
            message='When does the next batch start?',
            is_read=False,
        )

    def get(self, **params):
        return self.client.get('/api/private/contact-messages/', params, **self.auth).json()

    def test_search_by_name(self):
        self.assertEqual(self.get(search='Nusrat')['meta']['total'], 1)

    def test_search_by_message_body(self):
        body = self.get(search='videos')
        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['name'], 'Imran Hossain')

    def test_search_by_phone(self):
        self.assertEqual(self.get(search='01810600003')['meta']['total'], 1)

    def test_unread_filter(self):
        self.assertEqual(self.get(is_read='0')['meta']['total'], 2)
        self.assertEqual(self.get(is_read='1')['meta']['total'], 1)
        self.assertEqual(self.get()['meta']['total'], 3)

    def test_pages_do_not_overlap(self):
        seen = []
        for page in (1, 2, 3):
            seen.extend(r['id'] for r in self.get(page=page, per_page=1)['data'])
        self.assertEqual(len(seen), len(set(seen)), f'a message appeared twice: {seen}')
        self.assertEqual(len(seen), 3)
