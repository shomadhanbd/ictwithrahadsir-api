"""Golden response shapes and URL contracts."""

from django.test import TestCase
from django.urls import reverse

from apps.content.models import Advertisement, Page, Testimonial
from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Content, Course, CourseTeacher, Section
from apps.identity.models import User
from apps.profiles.models import TeacherProfile

#: Exactly what `/api/public/home/` returns, in order.
HOME_KEYS = [
    'courses',
    'advertisement',
    'testimonials',
    'counters',
    'suceesstorycounter',
    'instructors',
    'bannerImage',
]

#: Homepage and course-detail `instructors` share this key list; clients read it, so it stays fixed.
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
    'slug',
    'title',
    'subtitle',
    'summary',
    'thumbnail',
    'delivery',
    'is_online',
    'difficulty',
    'language',
    'duration',
    'class_level',
    'group',
    'batch',
    'is_featured',
    'student_count',
    'price',
    'is_free',
    'instructors',
    'starts_on',
    'enrollment_open',
    'lesson_counts',
    'enrollment',
    'has_purchased',
]

#: The course landing page: the card, then everything that sells it.
COURSE_DETAIL_KEYS = COURSE_LIST_KEYS + [
    'status',
    'description',
    'banner',
    'promo_video',
    'syllabus_pdf',
    'learning_outcomes',
    'target_audience',
    'requirements',
    'highlights',
    'faqs',
    'schedule',
    'routines',
    'packages',
    'curriculum',
    'seo',
]

#: An admin course-teacher row; only `commission` and `order` are editable.
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
        self.auth = bearer(self.admin)

        self.course = Course.objects.create(
            title='ICT',
            slug='ict',
            status='published',
            is_featured=True,
            thumbnail='http://localhost:8000/media/seed/course-0.png',
        )

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
            {'link': 'http://localhost:8000/media/seed/teacher-0.png'},
        )

    def test_course_list_payload_shape(self):
        body = self.client.get(reverse('api:courses:course_list')).json()
        self.assertEqual(list(body['data'][0].keys()), COURSE_LIST_KEYS)

    def test_course_detail_payload_shape(self):
        body = self.client.get(reverse('api:courses:course_detail', args=[self.course.slug])).json()
        self.assertEqual(list(body.keys()), COURSE_DETAIL_KEYS)
        self.assertEqual(list(body['lesson_counts'].keys()), ['video', 'note', 'pdf', 'exam', 'link', 'live', 'total'])
        self.assertEqual(list(body['schedule'].keys()), ['starts_on', 'ends_on', 'enrollment_deadline', 'note'])
        self.assertEqual(list(body['seo'].keys()), ['title', 'description', 'image'])

    def test_course_detail_instructors_shape(self):
        url = reverse('api:courses:course_detail', args=[self.course.slug])
        body = self.client.get(url).json()

        instructor = body['instructors'][0]
        self.assertEqual(list(instructor.keys()), PUBLIC_TEACHER_KEYS)
        self.assertEqual(instructor['name'], 'Rahad Sir')
        # MediaField renders a {link} object, not a bare URL.
        self.assertEqual(sorted(instructor['image'].keys()), ['link'])
        self.assertEqual(
            instructor['image']['link'],
            'http://localhost:8000/media/seed/teacher-0.png',
        )

    def test_admin_course_teacher_payload_shape(self):
        body = self.client.get(reverse('api:courses:admin_course_teacher_list'), **self.auth)
        self.assertEqual(list(body.json()['data'][0].keys()), ADMIN_COURSE_TEACHER_KEYS)


class AdminSearchTests(TestCase):
    """`?search=` must actually filter."""

    def setUp(self):
        from apps.content.models import Notice

        admin = User.objects.create_user(phone='01899000111', name='Admin', role=User.Role.ADMIN, is_staff=True)
        self.auth = bearer(admin)

        Notice.objects.create(slug=next_slug("notice"), title='Exam routine published')
        Notice.objects.create(slug=next_slug("notice"), title='Holiday announcement')
        Course.objects.create(slug=next_slug("course"), title='Physics crash course')
        Course.objects.create(slug=next_slug("course"), title='Chemistry masterclass')
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
        self.assert_filters(reverse('api:content:admin_notice_list'), 'Holiday', 1)

    def test_course_search_filters(self):
        self.assert_filters(reverse('api:courses:admin_course_list'), 'Physics', 1)

    def test_teacher_search_filters(self):
        self.assert_filters(reverse('api:profiles:admin_teacher_list'), 'Rahim', 1)

    def test_search_that_matches_nothing_returns_nothing(self):
        """The panel's empty state depends on this actually being empty."""
        url = reverse('api:content:admin_notice_list')
        body = self.client.get(url, {'search': 'zzzznomatch'}, **self.auth).json()
        self.assertEqual(body['meta']['total'], 0)
        self.assertEqual(body['data'], [])


class AdminCourseDetailTests(TestCase):
    """The admin panel opens a course by its id."""

    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.course = Course.objects.create(slug=next_slug("course"), title='Physics First Paper')

    def detail(self, value):
        return self.client.get(f'/api/private/courses/{value}/', **self.auth)

    def test_detail_by_pk(self):
        res = self.detail(self.course.pk)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['title'], 'Physics First Paper')

    def test_unknown_id_404s(self):
        self.assertEqual(self.detail(99999).status_code, 404)


class CourseTabSearchTests(TestCase):
    """The course tabs all ship a search box; each endpoint must honour it."""

    def setUp(self):
        from apps.courses.models import CourseTeacher, Enrollment, Routine

        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.course = Course.objects.create(slug=next_slug("course"), title='Search Tab Course')

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
        """Enrolment pages are stably ordered, so no student appears on two."""
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


class CourseMaterialCrudTests(TestCase):
    """Admins create, edit and delete course materials."""

    def setUp(self):
        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        self.course = Course.objects.create(slug=next_slug("course"), title='Material Host Course')

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

        other = Course.objects.create(slug=next_slug("course"), title='Another Course')
        CourseMaterial.objects.create(title='Mine', course=self.course)
        CourseMaterial.objects.create(title='Theirs', course=other)

        body = self.client.get('/api/private/course-materials/', {'course_id': self.course.pk}, **self.auth).json()
        self.assertEqual(body['meta']['total'], 1)
        self.assertEqual(body['data'][0]['title'], 'Mine')


class AdminPaymentListTests(TestCase):
    """The payments screen searches and filters on the server."""

    def setUp(self):
        from apps.billing.models import Payment, Product

        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)
        product = Product.objects.create(
            product_id=next_slug("product"), title='Paid Bundle', price=500, base_price=500
        )

        for name, phone, txn, status in [
            ('Nusrat Jahan', '01810500001', 'TRX-AAA-111', Payment.Status.INITIATED),
            ('Imran Hossain', '01810500002', 'TRX-BBB-222', Payment.Status.VALID),
            ('Rahim Uddin', '01810500003', 'TRX-CCC-333', Payment.Status.FAILED),
        ]:
            user = User.objects.create_user(phone=phone, name=name, role=User.Role.STUDENT)
            Payment.objects.create(user=user, product=product, amount=500, transaction_id=txn, status=status)

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
        self.assertEqual(self.get(status='INITIATED')['meta']['total'], 1)
        self.assertEqual(self.get(status='VALID')['meta']['total'], 1)
        self.assertEqual(self.get(status='all')['meta']['total'], 3)
        self.assertEqual(self.get()['meta']['total'], 3)

    def test_pages_do_not_overlap(self):
        seen = []
        for page in (1, 2, 3):
            seen.extend(r['id'] for r in self.get(page=page, per_page=1)['data'])
        self.assertEqual(len(seen), len(set(seen)), f'a payment appeared twice: {seen}')
        self.assertEqual(len(seen), 3)


class ContentSearchTests(TestCase):
    """Every content endpoint honours `?search=`."""

    def setUp(self):
        from apps.content.models import EBook, NoticeCategory

        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)

        NoticeCategory.objects.create(slug=next_slug("noticecategory"), title='Exam schedule')
        NoticeCategory.objects.create(slug=next_slug("noticecategory"), title='Holiday notice')
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
        """Each setting reports the value type its editor needs."""
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
