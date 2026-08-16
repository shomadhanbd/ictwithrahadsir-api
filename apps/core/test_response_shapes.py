"""Golden response-shape tests for the app re-decomposition.

`UrlContractTests` guards which *paths* are served. It says nothing about
what comes back from them, so it stays green while a serializer rewrite
silently changes the shape of a payload behind an unchanged URL. The app
re-decomposition does exactly that: extracting `Exam` off `Content` and
unifying `Teacher`/`Instructor` both rewrite serializer internals under
paths that must not move.

These assert exact key lists and the literal values that come from model
field defaults, so a shape change fails loudly. They live in `core`
because `core` survives the restructure with its name intact.

Key order matters: DRF emits keys in `Meta.fields` order, and the two
frontends destructure these payloads.
"""

from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token

from apps.identity.models import User
from apps.cms.models import Advertisement, Page, Testimonial
from apps.courses.models import Content, Course, CourseCategory, Instructor, Section
from apps.exams.models import McqStore
from apps.team.models import Teacher

#: Exactly what `/api/v1/home/` returns, in order.
HOME_KEYS = [
    'courses', 'courseCategories', 'advertisement', 'testimonials',
    'counters', 'suceesstorycounter', 'instructors', 'bannerImage',
]

#: Both the homepage `instructors` (team.Teacher) and course-detail
#: `instructors` (courses.Instructor) serialise to this same key list --
#: the unification must keep both byte-identical.
PUBLIC_INSTRUCTOR_KEYS = [
    'id', 'name', 'designation', 'description', 'type', 'order', 'image',
]

COURSE_LIST_KEYS = [
    'id', 'title', 'slug', 'subtitle', 'duration', 'is_online', 'active',
    'featured', 'fake_user_count', 'video_count', 'class_count', 'exam_count',
    'note_count', 'link_count', 'live_count', 'audio_count', 'online_count',
    'offline_count', 'image', 'price', 'categories', 'instructors', 'routines',
    'subscription_status', 'has_order', 'users_count',
]

ADMIN_INSTRUCTOR_KEYS = [
    'id', 'course_id', 'user_id', 'name', 'email', 'phone', 'designation',
    'description', 'institute', 'type', 'order', 'commission', 'image',
]

#: The ten flat exam fields the admin panel reads and writes on
#: /admin/contents/. They are contract, whatever model backs them.
EXAM_FIELD_KEYS = [
    'exam_store_id', 'exam_mode', 'exam_total_marks', 'exam_pass_marks',
    'exam_positive_marks', 'exam_negative_marks', 'exam_duration_minutes',
    'exam_start_time', 'exam_end_time', 'exam_result_publish_time',
]

#: What a content with NO exam configuration emits today. These come from
#: model field defaults, so once the fields move to a separate Exam row
#: that a video does not have, they must still be produced -- not nulls.
#: COERCE_DECIMAL_TO_STRING is not overridden, hence the strings.
NON_EXAM_DEFAULTS = {
    'exam_store_id': None,
    'exam_mode': 'exam',
    'exam_total_marks': None,
    'exam_pass_marks': None,
    'exam_positive_marks': '1.00',
    'exam_negative_marks': '0.00',
    'exam_duration_minutes': None,
    'exam_start_time': None,
    'exam_end_time': None,
    'exam_result_publish_time': None,
}


class ResponseShapeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            phone='01710900001', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.admin).key}'
        }

        self.category = CourseCategory.objects.create(title='HSC', slug='hsc')
        self.course = Course.objects.create(
            title='ICT', slug='ict', active=True, featured=True,
            image='http://localhost:8000/media/seed/course-0.png',
        )
        self.course.categories.add(self.category)

        self.teacher = Teacher.objects.create(
            name='Rahad Sir', designation='Founder', description='Bio',
            type=Teacher.Type.FOUNDER,
            image='http://localhost:8000/media/seed/teacher-0.png',
        )
        Instructor.objects.create(
            course=self.course, name='Rahad Sir', designation='Founder',
            description='Bio', type=Instructor.Type.FOUNDER,
            image='http://localhost:8000/media/seed/teacher-0.png',
        )

        Testimonial.objects.create(name='Student', description='Great', ratings=5)
        Advertisement.objects.create(title='Admission open')
        Page.objects.update_or_create(
            key='homeBannerImage',
            defaults={'slug': 'homeBannerImage', 'value_type': Page.ValueType.IMAGE},
        )

        self.section = Section.objects.create(
            course=self.course, title='Ch1', slug='ict-ch1'
        )
        self.exam_content = Content.objects.create(
            course=self.course, section=self.section, title='Exam',
            slug='ict-exam', type=Content.Type.EXAM,
            exam_store=McqStore.objects.create(title='Bank'),
            exam_total_marks=15, exam_pass_marks=8,
            exam_positive_marks=Decimal('1.00'),
            exam_negative_marks=Decimal('0.25'),
            exam_duration_minutes=15,
        )
        self.video_content = Content.objects.create(
            course=self.course, section=self.section, title='Video',
            slug='ict-video', type=Content.Type.VIDEO,
        )

    # -- public ----------------------------------------------------------

    def test_home_payload_shape(self):
        body = self.client.get(reverse('api:cms:v1:home')).json()
        self.assertEqual(list(body.keys()), HOME_KEYS)
        self.assertEqual(list(body['instructors'][0].keys()), PUBLIC_INSTRUCTOR_KEYS)
        self.assertEqual(list(body['courses'][0].keys()), COURSE_LIST_KEYS)

    def test_home_instructors_are_the_teacher_roster(self):
        body = self.client.get(reverse('api:cms:v1:home')).json()
        self.assertEqual(body['instructors'][0]['name'], 'Rahad Sir')
        self.assertEqual(body['instructors'][0]['type'], 'founder')
        self.assertEqual(
            body['instructors'][0]['image'],
            {'id': body['instructors'][0]['image']['id'],
             'link': 'http://localhost:8000/media/seed/teacher-0.png'},
        )

    def test_course_list_payload_shape(self):
        body = self.client.get(reverse('api:courses:v1:course_list')).json()
        self.assertEqual(list(body['data'][0].keys()), COURSE_LIST_KEYS)

    def test_course_detail_instructors_shape(self):
        url = reverse('api:courses:v1:course_detail', args=[self.course.slug])
        body = self.client.get(url).json()

        instructor = body['instructors'][0]
        self.assertEqual(list(instructor.keys()), PUBLIC_INSTRUCTOR_KEYS)
        self.assertEqual(instructor['name'], 'Rahad Sir')
        # MediaField renders a {id, link} object, not a bare URL.
        self.assertEqual(sorted(instructor['image'].keys()), ['id', 'link'])
        self.assertEqual(
            instructor['image']['link'],
            'http://localhost:8000/media/seed/teacher-0.png',
        )

    # -- admin -----------------------------------------------------------

    def test_admin_instructor_payload_shape(self):
        body = self.client.get(reverse('api:courses:v1:admin-instructor-list'), **self.auth)
        self.assertEqual(list(body.json()['data'][0].keys()), ADMIN_INSTRUCTOR_KEYS)

    def test_admin_content_exposes_the_flat_exam_fields(self):
        url = reverse('api:courses:v1:admin-content-detail', args=[self.exam_content.slug])
        body = self.client.get(url, **self.auth).json()

        for key in EXAM_FIELD_KEYS:
            self.assertIn(key, body, f'{key} disappeared from the admin content payload')
        self.assertEqual(body['exam_total_marks'], 15)
        self.assertEqual(body['exam_positive_marks'], '1.00')
        self.assertEqual(body['exam_negative_marks'], '0.25')

    def test_non_exam_content_still_emits_the_exam_field_defaults(self):
        # The trap in the Exam extraction: these values come from model
        # field defaults today, so a video reports exam_mode="exam" and
        # "1.00"/"0.00" even though it is not an exam. Once the fields live
        # on a separate Exam row that a video has no instance of, the
        # serializer has to reproduce them rather than emit nulls.
        url = reverse('api:courses:v1:admin-content-detail', args=[self.video_content.slug])
        body = self.client.get(url, **self.auth).json()

        actual = {key: body[key] for key in EXAM_FIELD_KEYS}
        self.assertEqual(actual, NON_EXAM_DEFAULTS)

    def test_admin_content_accepts_the_flat_exam_fields_on_write(self):
        url = reverse('api:courses:v1:admin-content-detail', args=[self.exam_content.slug])
        response = self.client.patch(
            url, {'exam_total_marks': 40, 'exam_pass_marks': 20},
            content_type='application/json', **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['exam_total_marks'], 40)

    # -- exam taking -----------------------------------------------------

    def test_exam_detail_payload_shape(self):
        student = User.objects.create_user(
            phone='01810900001', name='Student', password='Str0ngPass!23'
        )
        from apps.courses.models import CourseUser

        CourseUser.objects.create(course=self.course, user=student)
        auth = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=student).key}'}

        url = reverse('api:exams:v1:exam_detail', args=[self.exam_content.pk])
        body = self.client.get(url, **auth).json()

        self.assertEqual(
            list(body.keys()),
            ['id', 'title', 'duration', 'total_marks', 'pass_marks',
             'positive_marks', 'negative_marks', 'start_time', 'end_time',
             'result_publish_time', 'result_published', 'question', 'result'],
        )
        # The exam is addressed by its Content id -- the extraction must
        # not change which id appears here.
        self.assertEqual(body['id'], self.exam_content.pk)
        self.assertEqual(body['question']['exam_id'], self.exam_content.pk)
