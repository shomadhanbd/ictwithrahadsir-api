"""Which role may reach which admin endpoint."""

from django.urls import get_resolver
from django.urls.resolvers import URLResolver

from rest_framework.test import APITestCase

from apps.academic.models import ClassLevel, Group, Subject
from apps.core.testing import bearer, next_slug
from apps.identity.models import User


def served_paths(resolver=None, prefix=''):
    """Yield the full path expression of every leaf route in the URLconf."""
    for entry in (resolver or get_resolver()).url_patterns:
        pattern = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from served_paths(entry, pattern)
        else:
            yield pattern


API = '/api'

#: Admins only: accounts, money, pricing, and who teaches what.
FULL_ADMIN_ONLY = [
    f'{API}/private/payments/',
    f'{API}/private/products/',
    f'{API}/private/materials/book-orders/',
    f'{API}/private/materials/delivery-rates/',
    f'{API}/private/teachers/',
    f'{API}/private/course-teachers/',
    f'{API}/private/dashboard/sales-overview/',
    f'{API}/private/dashboard/payment-chart/',
]

#: The curriculum: admins and teachers build it; only admins delete from it.
CURRICULUM = [
    f'{API}/private/subjects/',
    f'{API}/private/class-levels/',
    f'{API}/private/chapters/',
    f'{API}/private/topics/',
]

#: Admins write, teachers read.
ADMIN_WRITE_TEACHER_READ = [
    f'{API}/private/groups/',
    f'{API}/private/batches/',
]

#: Admins and teachers; whom a teacher may act on is checked per object (`CanManageUsers`).
USER_MANAGEMENT = [
    f'{API}/private/users/',
]

#: Admins and moderators: the published site.
CONTENT_STAFF = [
    f'{API}/private/notices/',
    f'{API}/private/notice-categories/',
    f'{API}/private/feedback/',
    f'{API}/private/website/banners/',
    f'{API}/private/materials/topics/',
    f'{API}/private/materials/categories/',
    f'{API}/private/materials/items/',
    f'{API}/private/website/sections/',
]

#: Admins and teachers: courses and everything taught inside them.
TEACHING_STAFF = [
    f'{API}/private/courses/',
    f'{API}/private/sections/',
    f'{API}/private/contents/',
    f'{API}/private/routines/',
    # The question bank and the exams built from it.
    f'{API}/private/question-blocks/',
    f'{API}/private/question-blocks/save/',
    f'{API}/private/question-counts/refresh/',
    f'{API}/private/question-sources/',
    f'{API}/private/question-types/',
    f'{API}/private/exams/',
    f'{API}/private/exam-sections/',
    f'{API}/private/users/search/',
    f'{API}/private/dashboard/',
]


class RoleMatrixTests(APITestCase):
    """One GET per endpoint per role. 200 means allowed, 403 means refused."""

    def setUp(self):
        super().setUp()
        self.tokens = {}
        for role in (User.Role.ADMIN, User.Role.TEACHER, User.Role.MODERATOR, User.Role.STUDENT):
            user = User.objects.create_user(
                phone=f'0171000{abs(hash(role)) % 10000:04d}',
                name=role.label,
                password='Str0ngPass!23',
                role=role,
            )
            self.tokens[role] = bearer(user)

    def assert_reachable(self, paths, role, *, allowed):
        for path in paths:
            with self.subTest(role=role, path=path):
                status = self.client.get(path, **self.tokens[role]).status_code
                if allowed:
                    self.assertNotEqual(status, 403, f'{role} was refused {path}')
                else:
                    self.assertEqual(status, 403, f'{role} reached {path} (got {status})')

    def test_admin_reaches_every_tier(self):
        for group in (
            FULL_ADMIN_ONLY,
            CONTENT_STAFF,
            TEACHING_STAFF,
            USER_MANAGEMENT,
            CURRICULUM,
            ADMIN_WRITE_TEACHER_READ,
        ):
            self.assert_reachable(group, User.Role.ADMIN, allowed=True)

    def test_moderator_manages_site_content(self):
        self.assert_reachable(CONTENT_STAFF, User.Role.MODERATOR, allowed=True)

    def test_moderator_is_kept_out_of_accounts_and_money(self):
        self.assert_reachable(FULL_ADMIN_ONLY, User.Role.MODERATOR, allowed=False)

    def test_moderator_is_kept_out_of_course_material(self):
        self.assert_reachable(TEACHING_STAFF, User.Role.MODERATOR, allowed=False)

    def test_moderator_is_kept_out_of_student_accounts(self):
        self.assert_reachable(USER_MANAGEMENT, User.Role.MODERATOR, allowed=False)

    def test_teacher_manages_course_material(self):
        self.assert_reachable(TEACHING_STAFF, User.Role.TEACHER, allowed=True)

    def test_teacher_is_kept_out_of_accounts_and_money(self):
        """Admin-only endpoints refuse a teacher."""
        self.assert_reachable(FULL_ADMIN_ONLY, User.Role.TEACHER, allowed=False)

    def test_teacher_reads_the_academic_taxonomy(self):
        """A teacher can read the curriculum the exam builder files questions under."""
        self.assert_reachable(CURRICULUM + ADMIN_WRITE_TEACHER_READ, User.Role.TEACHER, allowed=True)

    def test_teacher_builds_the_curriculum(self):
        """A teacher can build the curriculum, level by level."""
        auth = self.tokens[User.Role.TEACHER]

        def create(path, body):
            response = self.client.post(f'{API}/private/{path}/', body, format='json', **auth)
            self.assertEqual(response.status_code, 201, response.content)
            return response.json()['id']

        group_id = Group.objects.create(slug=next_slug("group"), name='বিজ্ঞান').pk

        level = create('class-levels', {'name': 'দ্বাদশ', 'slug': 'class-12'})
        subject = create(
            'subjects', {'name': 'আইসিটি', 'slug': 'ict-12', 'class_level_id': level, 'group_id': group_id}
        )
        chapter = create(
            'chapters', {'name': 'সংখ্যা পদ্ধতি', 'slug': 'number-systems', 'subject_id': subject, 'chapter_number': 3}
        )
        create('topics', {'name': 'বাইনারি', 'slug': 'binary', 'chapter_id': chapter})

        renamed = self.client.patch(
            f'{API}/private/chapters/{chapter}/', {'name': 'Number systems'}, format='json', **auth
        )
        self.assertEqual(renamed.status_code, 200)

    def test_only_an_admin_deletes_part_of_the_curriculum(self):
        level = ClassLevel.objects.create(slug=next_slug("classlevel"), name='অষ্টম')
        path = f'{API}/private/class-levels/{level.pk}/'

        self.assertEqual(self.client.delete(path, **self.tokens[User.Role.TEACHER]).status_code, 403)
        self.assertEqual(self.client.delete(path, **self.tokens[User.Role.ADMIN]).status_code, 204)

    def test_each_refusal_names_what_was_refused(self):
        level = ClassLevel.objects.create(slug=next_slug("classlevel"), name='নবম')
        group = Group.objects.create(slug=next_slug("group"), name='মানবিক')
        subject = Subject.objects.create(slug=next_slug("subject"), name='বাংলা', class_level=level, group=group)
        staff_only = 'Only an admin or teacher may manage course material.'
        cases = [
            (User.Role.STUDENT, 'get', f'{API}/private/subjects/', staff_only),
            (
                User.Role.TEACHER,
                'delete',
                f'{API}/private/subjects/{subject.pk}/',
                'Only an admin may delete part of the curriculum.',
            ),
            (User.Role.STUDENT, 'get', f'{API}/private/groups/', staff_only),
        ]
        for role, method, path, message in cases:
            with self.subTest(role=role, method=method, path=path):
                response = getattr(self.client, method)(path, format='json', **self.tokens[role])
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.json(), {'message': message})

    def test_teacher_cannot_change_groups_or_batches(self):
        for path in ADMIN_WRITE_TEACHER_READ:
            with self.subTest(path=path):
                response = self.client.post(
                    path,
                    {'name': 'Nope'},
                    content_type='application/json',
                    **self.tokens[User.Role.TEACHER],
                )
                self.assertEqual(response.status_code, 403, path)

    def test_moderator_is_kept_out_of_the_academic_taxonomy(self):
        self.assert_reachable(CURRICULUM + ADMIN_WRITE_TEACHER_READ, User.Role.MODERATOR, allowed=False)

    def test_students_and_moderators_cannot_build_the_curriculum(self):
        for role in (User.Role.STUDENT, User.Role.MODERATOR):
            for path in CURRICULUM:
                with self.subTest(role=role, path=path):
                    response = self.client.post(path, {'name': 'Nope'}, format='json', **self.tokens[role])
                    self.assertEqual(response.status_code, 403, path)

    def test_teacher_is_kept_out_of_site_content(self):
        self.assert_reachable(CONTENT_STAFF, User.Role.TEACHER, allowed=False)

    def test_teacher_still_reaches_the_student_roster(self):
        """A teacher reaches the user list; what they may do to an account is checked per object."""
        self.assert_reachable(USER_MANAGEMENT, User.Role.TEACHER, allowed=True)

    def test_a_student_reaches_no_admin_endpoint(self):
        for group in (
            FULL_ADMIN_ONLY,
            CONTENT_STAFF,
            TEACHING_STAFF,
            USER_MANAGEMENT,
            ADMIN_WRITE_TEACHER_READ,
        ):
            self.assert_reachable(group, User.Role.STUDENT, allowed=False)


class EveryAdminPathHasADecidedTierTests(APITestCase):
    """No admin endpoint should be missing from the table above."""

    #: Paths the matrix cannot GET; each is covered by its own app's tests.
    NOT_GETTABLE = {
        'api/private/enrollments/',
        'api/private/payments/cash/',
        'api/private/payments/cash/packages/',
        'api/private/teachers/lookup/',
        'api/private/uploads/',
    }

    def test_the_matrix_covers_every_admin_collection(self):
        listed = {
            p.removeprefix(f'{API}/')
            for p in FULL_ADMIN_ONLY
            + CONTENT_STAFF
            + TEACHING_STAFF
            + USER_MANAGEMENT
            + CURRICULUM
            + ADMIN_WRITE_TEACHER_READ
        }

        contract = list(served_paths())

        # Routers spell a route `api/^private/x/$` or `api/private/^x/$`; both become `private/x/`.
        def as_collection(raw):
            return raw.removeprefix('api/').replace('^', '').rstrip('$')

        skip = {as_collection(p) for p in self.NOT_GETTABLE}
        collections = {
            as_collection(p)
            for p in contract
            if p.startswith(('api/private/', 'api/^private/')) and '<' not in p and as_collection(p) not in skip
        }

        missing = sorted(collections - listed)
        self.assertEqual(
            missing,
            [],
            'These admin endpoints are not in the role matrix, so nobody has '
            'decided who may reach them:\n  ' + '\n  '.join(missing),
        )


class TeacherCourseScopingTests(APITestCase):
    """A teacher's reach stops at the courses they actually teach."""

    def setUp(self):
        super().setUp()
        from apps.courses.models import Content, Course, CourseTeacher, Section
        from apps.profiles.models import TeacherProfile

        self.mine = Course.objects.create(title='My Course', slug='my-course')
        self.theirs = Course.objects.create(title='Their Course', slug='their-course')

        self.teacher_user = User.objects.create_user(
            phone='01710002001',
            name='Rahad',
            password='Str0ngPass!23',
            role=User.Role.TEACHER,
        )
        # Holding a teacher profile is what makes a user a teacher.
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)
        CourseTeacher.objects.create(user=self.teacher_user, course=self.mine)

        other_user = User.objects.create_user(
            phone='01710002002',
            name='Karim',
            password='Str0ngPass!23',
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=other_user)
        CourseTeacher.objects.create(user=other_user, course=self.theirs)

        self.admin = User.objects.create_user(
            phone='01710002003',
            name='Admin',
            password='Str0ngPass!23',
            role=User.Role.ADMIN,
            is_staff=True,
        )

        self.auth = self._auth(self.teacher_user)
        self.admin_auth = self._auth(self.admin)

        section = Section.objects.create(course=self.theirs, title='Week 1')
        self.their_content = Content.objects.create(
            course=self.theirs, section=section, title='Lesson', type=Content.Type.NOTE
        )

    def _auth(self, user):
        return bearer(user)

    def test_a_teacher_lists_only_their_own_courses(self):
        titles = [row['title'] for row in self.client.get(f'{API}/private/courses/', **self.auth).json()['data']]
        self.assertEqual(titles, ['My Course'])

    def test_an_admin_still_lists_every_course(self):
        titles = {row['title'] for row in self.client.get(f'{API}/private/courses/', **self.admin_auth).json()['data']}
        self.assertEqual(titles, {'My Course', 'Their Course'})

    def test_a_teacher_lists_only_their_own_lessons(self):
        listed = self.client.get(f'{API}/private/contents/', **self.auth).json()['data']
        self.assertEqual(listed, [])

    def test_a_teacher_cannot_open_another_teachers_course(self):
        response = self.client.get(f'{API}/private/courses/{self.theirs.pk}/', **self.auth)
        self.assertIn(response.status_code, (403, 404))

    def test_a_teacher_can_open_their_own_course(self):
        response = self.client.get(f'{API}/private/courses/{self.mine.pk}/', **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_teacher_cannot_edit_another_teachers_course(self):
        response = self.client.patch(f'{API}/private/courses/{self.theirs.pk}/', {'title': 'Hijacked'}, **self.auth)
        self.assertIn(response.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, 'Their Course')

    def test_a_teacher_cannot_toggle_another_teachers_lesson(self):
        """The toggle endpoint checks course access itself."""
        was_active = self.their_content.active
        response = self.client.post(
            f'{API}/private/contents/{self.their_content.pk}/toggle/',
            {'action': 'active'},
            format='json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.their_content.refresh_from_db()
        self.assertEqual(self.their_content.active, was_active)

    def test_a_teacher_cannot_read_another_courses_enrolments(self):
        response = self.client.get(f'{API}/private/courses/{self.theirs.pk}/enrollments/', **self.auth)
        self.assertEqual(response.status_code, 403)

    def test_a_teacher_can_read_their_own_courses_enrolments(self):
        response = self.client.get(f'{API}/private/courses/{self.mine.pk}/enrollments/', **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_teacher_reaches_a_course_the_moment_they_are_assigned(self):
        """Nothing has to be pushed anywhere for access to follow."""
        from apps.courses.models import CourseTeacher

        # 404, not 403: the scoping mixin filters an unassigned course out.
        self.assertIn(
            self.client.get(f'{API}/private/courses/{self.theirs.pk}/', **self.auth).status_code,
            (403, 404),
        )

        CourseTeacher.objects.create(user=self.teacher_user, course=self.theirs)

        self.assertEqual(self.client.get(f'{API}/private/courses/{self.theirs.pk}/', **self.auth).status_code, 200)
