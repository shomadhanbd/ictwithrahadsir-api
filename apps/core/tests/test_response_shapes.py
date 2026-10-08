"""Golden response shapes and URL contracts."""

from django.test import TestCase
from django.urls import reverse

from apps.core.testing import bearer, make_user, next_slug
from apps.courses.models import Content, Course, CourseTeacher, Section
from apps.feedback.models import Feedback
from apps.identity.models import User
from apps.profiles.models import TeacherProfile
from apps.website.models import Banner

#: Exactly what `/api/public/home/` returns, in order.
HOME_KEYS = ['courses', 'banners', 'testimonials', 'stats', 'instructors']

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

        Feedback.objects.create(
            source='general', name='Student', comment='Great', rating=5, status='approved', is_featured=True
        )
        Banner.objects.create(title='Admission open', image='https://example.com/banner.jpg')

        self.section = Section.objects.create(course=self.course, title='Ch1')
        self.exam_content = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Exam',
            type=Content.Type.EXAM,
        )
        self.video_content = Content.objects.create(
            course=self.course,
            section=self.section,
            title='Video',
            type=Content.Type.VIDEO,
        )

    def test_home_payload_shape(self):
        body = self.client.get(reverse('api:website:home')).json()
        self.assertEqual(list(body.keys()), HOME_KEYS)
        self.assertEqual(list(body['instructors'][0].keys()), PUBLIC_TEACHER_KEYS)
        self.assertEqual(list(body['courses'][0].keys()), COURSE_LIST_KEYS)

    def test_home_instructors_are_the_teacher_roster(self):
        body = self.client.get(reverse('api:website:home')).json()
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
        from apps.communication.models import Notice

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
        self.assert_filters(reverse('api:communication:admin_notice_list'), 'Holiday', 1)

    def test_course_search_filters(self):
        self.assert_filters(reverse('api:courses:admin_course_list'), 'Physics', 1)

    def test_teacher_search_filters(self):
        self.assert_filters(reverse('api:profiles:admin_teacher_list'), 'Rahim', 1)

    def test_search_that_matches_nothing_returns_nothing(self):
        """The panel's empty state depends on this actually being empty."""
        url = reverse('api:communication:admin_notice_list')
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


class ContentSearchTests(TestCase):
    """Every content endpoint honours `?search=`."""

    def setUp(self):
        from apps.communication.models import NoticeCategory

        admin = make_user(role=User.Role.ADMIN)
        self.auth = bearer(admin)

        NoticeCategory.objects.create(slug=next_slug("noticecategory"), title='Exam schedule')
        NoticeCategory.objects.create(slug=next_slug("noticecategory"), title='Holiday notice')
        Feedback.objects.create(source='general', name='Nusrat Jahan', comment='Great course', rating=5)
        Feedback.objects.create(source='general', name='Imran Hossain', comment='Very helpful', rating=4)

    def assert_filters(self, path, term, expected):
        unfiltered = self.client.get(path, **self.auth).json()['meta']['total']
        filtered = self.client.get(path, {'search': term}, **self.auth).json()['meta']['total']
        self.assertEqual(filtered, expected, f'{path} ?search={term}')
        self.assertLess(filtered, unfiltered, f'{path} ignored ?search=')

    def test_notice_category_search(self):
        self.assert_filters('/api/private/notice-categories/', 'Holiday', 1)

    def test_feedback_search(self):
        self.assert_filters('/api/private/feedback/', 'Nusrat', 1)
