"""Contract tests for the teacher roster and per-course assignments.

This app had no tests at all, which mattered more than the small file size
suggests: `CourseInstructor.save()` copies four fields down from the linked
`Teacher`, and `InstructorSerializer.create()` will invent a `Teacher` when
none is given. Both are silent behaviours that nothing was pinning.
"""

from django.urls import reverse

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from apps.courses.models import Course
from apps.faculty.models import CourseInstructor, Teacher
from apps.identity.models import User

TEACHERS_URL = reverse('api:faculty:v1:admin-team-list')
LOOKUP_URL = reverse('api:faculty:v1:admin_teacher_lookup')
INSTRUCTORS_URL = reverse('api:faculty:v1:admin-instructor-list')


class FacultyTestBase(APITestCase):
    def setUp(self):
        admin = User.objects.create_user(
            phone='01710700001', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )
        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=admin).key}'
        }
        self.student = User.objects.create_user(
            phone='01710700002', name='Student', password='Str0ngPass!23',
        )
        self.student_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=self.student).key}'
        }
        self.teacher = Teacher.objects.create(
            name='Rahad Sir', designation='Lead Instructor', description='ICT',
        )
        self.course = Course.objects.create(title='ICT', slug='ict', active=True)


class TeacherRosterTests(FacultyTestBase):
    def test_the_roster_is_admin_only(self):
        self.assertEqual(self.client.get(TEACHERS_URL, **self.student_auth).status_code, 403)
        self.assertEqual(self.client.get(TEACHERS_URL).status_code, 401)

    def test_the_roster_lists_teachers(self):
        response = self.client.get(TEACHERS_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['meta']['total'], 1)
        self.assertEqual(response.data['data'][0]['name'], 'Rahad Sir')

    def test_the_lookup_is_unpaginated_and_wrapped_in_data(self):
        """The panel renders this straight into a dropdown, so it has no
        pagination block -- but the payload still sits under `data`."""
        response = self.client.get(LOOKUP_URL, **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.data), ['data'])
        self.assertEqual(len(response.data['data']), 1)

    def test_search_actually_filters(self):
        Teacher.objects.create(name='Someone Else')
        response = self.client.get(f'{TEACHERS_URL}?search=Rahad', **self.auth)
        self.assertEqual(response.data['meta']['total'], 1)


class CourseInstructorTests(FacultyTestBase):
    def test_assigning_a_teacher_copies_their_details_down(self):
        """Blank per-course fields are filled from the linked teacher, so the
        public payload is identical whether or not anyone overrode anything."""
        assignment = CourseInstructor.objects.create(
            course=self.course, teacher=self.teacher
        )
        self.assertEqual(assignment.name, 'Rahad Sir')
        self.assertEqual(assignment.designation, 'Lead Instructor')

    def test_a_per_course_override_is_kept(self):
        assignment = CourseInstructor.objects.create(
            course=self.course, teacher=self.teacher, designation='Guest Lecturer',
        )
        self.assertEqual(assignment.name, 'Rahad Sir')
        self.assertEqual(assignment.designation, 'Guest Lecturer')

    def test_creating_without_a_teacher_id_creates_the_roster_entry(self):
        """The admin panel posts flat fields with no `teacher_id`; the
        assignment must still end up linked to a real roster teacher."""
        response = self.client.post(
            INSTRUCTORS_URL,
            {'course_id': self.course.pk, 'name': 'New Teacher', 'designation': 'Tutor'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
        assignment = CourseInstructor.objects.get(name='New Teacher')
        self.assertIsNotNone(assignment.teacher_id)
        self.assertTrue(Teacher.objects.filter(name='New Teacher').exists())

    def test_the_course_id_filter_narrows_the_list(self):
        other = Course.objects.create(title='Other', slug='other', active=True)
        CourseInstructor.objects.create(course=self.course, teacher=self.teacher)
        CourseInstructor.objects.create(course=other, teacher=self.teacher)

        response = self.client.get(f'{INSTRUCTORS_URL}?course_id={self.course.pk}', **self.auth)
        self.assertEqual(response.data['meta']['total'], 1)
        self.assertEqual(
            self.client.get(INSTRUCTORS_URL, **self.auth).data['meta']['total'], 2
        )

    def test_instructors_are_admin_only(self):
        self.assertEqual(
            self.client.get(INSTRUCTORS_URL, **self.student_auth).status_code, 403
        )


class TeacherPropagationTests(FacultyTestBase):
    """Renaming a teacher must reach the course pages that show their name.

    `CourseInstructor` copies the teacher's details down so a per-course
    override is possible. Before `apps/faculty/signals.py` existed, that copy
    was only ever written when the assignment itself was saved, so a rename
    left every course page showing the old name for good.
    """

    def setUp(self):
        super().setUp()
        self.other_course = Course.objects.create(title='Other', slug='other', active=True)
        self.inherited = CourseInstructor.objects.create(
            course=self.course, teacher=self.teacher
        )
        self.overridden = CourseInstructor.objects.create(
            course=self.other_course, teacher=self.teacher, designation='Guest Lecturer'
        )

    def test_renaming_a_teacher_updates_their_assignments(self):
        self.teacher.name = 'Dr. Rahad Hossain'
        self.teacher.save()

        self.inherited.refresh_from_db()
        self.assertEqual(self.inherited.name, 'Dr. Rahad Hossain')

    def test_a_per_course_override_is_not_overwritten(self):
        """The whole point of the copied columns is that they can differ."""
        self.teacher.designation = 'Head of ICT'
        self.teacher.save()

        self.inherited.refresh_from_db()
        self.overridden.refresh_from_db()
        self.assertEqual(self.inherited.designation, 'Head of ICT')
        self.assertEqual(self.overridden.designation, 'Guest Lecturer')

    def test_untouched_fields_are_left_alone(self):
        self.teacher.name = 'Renamed'
        self.teacher.save()

        self.overridden.refresh_from_db()
        self.assertEqual(self.overridden.designation, 'Guest Lecturer')

    def test_creating_a_teacher_touches_nothing(self):
        Teacher.objects.create(name='Someone New')
        self.inherited.refresh_from_db()
        self.assertEqual(self.inherited.name, 'Rahad Sir')

    def test_the_rename_reaches_assignments_saved_through_the_api(self):
        """The admin panel edits teachers through a ModelViewSet, which is
        exactly the write path a service call would have missed."""
        response = self.client.patch(
            reverse('api:faculty:v1:admin-team-detail', args=[self.teacher.pk]),
            {'name': 'Via The Panel'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)

        self.inherited.refresh_from_db()
        self.assertEqual(self.inherited.name, 'Via The Panel')
