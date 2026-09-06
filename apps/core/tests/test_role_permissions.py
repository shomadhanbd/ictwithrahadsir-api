"""Which role may reach which admin endpoint.

There used to be one answer for the whole panel: `IsAdminRole` admitted
admins and instructors alike, on every `/admin/*` route and every method. A
teacher could open the payments screen, edit any account, and issue discount
codes; nobody could be given the notices desk without also being given all of
that.

Three tiers replace it (`apps.core.api.permissions`), and this is the table
that says what they mean. It is deliberately written as data: a new admin
endpoint should be added to one of the three lists below, and any endpoint in
none of them is one whose access nobody has decided.
"""


from rest_framework.authtoken.models import Token

from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import User

API = '/api/v1'

#: Admins only: accounts, money, pricing, and who teaches what.
FULL_ADMIN_ONLY = [
    f'{API}/admin/payments/',
    f'{API}/admin/dashboard/',
    f'{API}/admin/dashboard/sales-overview/',
    f'{API}/admin/dashboard/payment-chart/',
    f'{API}/admin/prices/',
    f'{API}/admin/coupons/',
    f'{API}/admin/teachers/',
    f'{API}/admin/instructors/',
    f'{API}/admin/sms-balance/',
]

#: Its own case: admins manage anybody, teachers manage students only, and
#: moderators are kept out entirely. The collection is reachable by both
#: admins and teachers; who they may act *on* is object-level and lives in
#: `apps.identity.api.v1.permissions.CanManageUsers` (tested there).
USER_MANAGEMENT = [
    f'{API}/admin/users/',
]

#: Admins and moderators: the published site and the contact inbox.
CONTENT_STAFF = [
    f'{API}/admin/notices/',
    f'{API}/admin/notice-categories/',
    f'{API}/admin/testimonials/',
    f'{API}/admin/advertisements/',
    f'{API}/admin/ebooks/',
    f'{API}/admin/pages/',
    f'{API}/admin/products/',
    f'{API}/admin/contact-messages/',
]

#: Admins and teachers: courses and everything taught inside them.
TEACHING_STAFF = [
    f'{API}/admin/courses/',
    f'{API}/admin/course-categories/',
    f'{API}/admin/sections/',
    f'{API}/admin/contents/',
    f'{API}/admin/course-materials/',
    f'{API}/admin/routines/',
    f'{API}/admin/mcq-folders/',
    f'{API}/admin/mcq-questions/',
    f'{API}/admin/exam-results/',
    f'{API}/admin/users/search/',
]


class RoleMatrixTests(ThrottledAPITestCase):
    """One GET per endpoint per role. 200 means allowed, 403 means refused."""

    def setUp(self):
        super().setUp()
        self.tokens = {}
        for role in (User.Role.ADMIN, User.Role.INSTRUCTOR, User.Role.MODERATOR,
                     User.Role.STUDENT):
            user = User.objects.create_user(
                phone=f'0171000{abs(hash(role)) % 10000:04d}',
                name=role.label,
                password='Str0ngPass!23',
                role=role,
            )
            self.tokens[role] = {
                'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=user).key}'
            }

    def assert_reachable(self, paths, role, *, allowed):
        for path in paths:
            with self.subTest(role=role, path=path):
                status = self.client.get(path, **self.tokens[role]).status_code
                if allowed:
                    self.assertNotEqual(
                        status, 403, f'{role} was refused {path}'
                    )
                else:
                    self.assertEqual(
                        status, 403, f'{role} reached {path} (got {status})'
                    )

    # -- admin sees everything ------------------------------------------
    def test_admin_reaches_every_tier(self):
        for group in (FULL_ADMIN_ONLY, CONTENT_STAFF, TEACHING_STAFF, USER_MANAGEMENT):
            self.assert_reachable(group, User.Role.ADMIN, allowed=True)

    # -- moderator: the content desk, and nothing else -------------------
    def test_moderator_manages_site_content(self):
        self.assert_reachable(CONTENT_STAFF, User.Role.MODERATOR, allowed=True)

    def test_moderator_is_kept_out_of_accounts_and_money(self):
        self.assert_reachable(FULL_ADMIN_ONLY, User.Role.MODERATOR, allowed=False)

    def test_moderator_is_kept_out_of_course_material(self):
        self.assert_reachable(TEACHING_STAFF, User.Role.MODERATOR, allowed=False)

    def test_moderator_is_kept_out_of_student_accounts(self):
        self.assert_reachable(USER_MANAGEMENT, User.Role.MODERATOR, allowed=False)

    # -- teacher: courses, and nothing else ------------------------------
    def test_teacher_manages_course_material(self):
        self.assert_reachable(TEACHING_STAFF, User.Role.INSTRUCTOR, allowed=True)

    def test_teacher_is_kept_out_of_accounts_and_money(self):
        """The headline regression: before the split, every one of these was
        open to any instructor."""
        self.assert_reachable(FULL_ADMIN_ONLY, User.Role.INSTRUCTOR, allowed=False)

    def test_teacher_is_kept_out_of_site_content(self):
        self.assert_reachable(CONTENT_STAFF, User.Role.INSTRUCTOR, allowed=False)

    def test_teacher_still_reaches_the_student_roster(self):
        """Deliberately not admin-only: a teacher enrols students on their own
        courses. What they may do to a given account is checked per object."""
        self.assert_reachable(USER_MANAGEMENT, User.Role.INSTRUCTOR, allowed=True)

    # -- student: none of it ---------------------------------------------
    def test_a_student_reaches_no_admin_endpoint(self):
        for group in (FULL_ADMIN_ONLY, CONTENT_STAFF, TEACHING_STAFF, USER_MANAGEMENT):
            self.assert_reachable(group, User.Role.STUDENT, allowed=False)


class EveryAdminPathHasADecidedTierTests(ThrottledAPITestCase):
    """No admin endpoint should be missing from the table above.

    An endpoint nobody has classified is one still running on whatever its
    base class defaults to, which is how the original single-tier sprawl
    happened in the first place.
    """

    #: Paths the matrix cannot GET: writes, detail routes needing a real pk,
    #: and the two logout/import actions. Each is covered by its own app's
    #: tests instead.
    NOT_GETTABLE = {
        'api/v1/admin/auth/logout/',
        'api/v1/admin/users/import/',
        'api/v1/admin/enrollments/',
        'api/v1/admin/teachers/lookup/',
    }

    def test_the_matrix_covers_every_admin_collection(self):
        listed = {p.removeprefix(f'{API}/') for p in
                  FULL_ADMIN_ONLY + CONTENT_STAFF + TEACHING_STAFF + USER_MANAGEMENT}

        contract = (
            (__import__('pathlib').Path(__file__).resolve().parent.parent
             / 'url_contract.txt').read_text().split()
        )
        collections = {
            path for path in contract
            if path.startswith('api/v1/^admin/') and path.endswith('/$')
            and '(?P<' not in path
        }
        collections = {p.replace('api/v1/^', '').rstrip('$') for p in collections}
        collections |= {
            p.removeprefix('api/v1/') for p in contract
            if p.startswith('api/v1/admin/') and '<' not in p
            and p not in self.NOT_GETTABLE
        }

        missing = sorted(collections - listed)
        self.assertEqual(
            missing, [],
            'These admin endpoints are not in the role matrix, so nobody has '
            'decided who may reach them:\n  ' + '\n  '.join(missing),
        )


class TeacherCourseScopingTests(ThrottledAPITestCase):
    """A teacher's reach stops at the courses they actually teach.

    `faculty.CourseInstructor.user` has existed since the faculty rewrite and
    was never once read for access -- being on a course's staff list and being
    allowed to edit that course were unrelated facts. This is what connects
    them, and `faculty.Teacher.user` is what connects the roster entry to a
    login in the first place.

    Both halves are checked, because each leaves a hole the other closes: the
    queryset filter hides other courses from the *list*, and the object
    permission stops them being reached *by id* anyway.
    """

    def setUp(self):
        super().setUp()
        from apps.courses.models import Content, Course, Section
        from apps.faculty.models import CourseInstructor, Teacher

        self.mine = Course.objects.create(title='My Course', slug='my-course')
        self.theirs = Course.objects.create(title='Their Course', slug='their-course')

        self.teacher_user = User.objects.create_user(
            phone='01710002001', name='Rahad', password='Str0ngPass!23',
            role=User.Role.INSTRUCTOR,
        )
        # The roster entry and the login are the same person -- that link is
        # the whole point of Teacher.user.
        self.teacher = Teacher.objects.create(name='Rahad', user=self.teacher_user)
        CourseInstructor.objects.create(teacher=self.teacher, course=self.mine, name='Rahad')

        other_user = User.objects.create_user(
            phone='01710002002', name='Karim', password='Str0ngPass!23',
            role=User.Role.INSTRUCTOR,
        )
        other = Teacher.objects.create(name='Karim', user=other_user)
        CourseInstructor.objects.create(teacher=other, course=self.theirs, name='Karim')

        self.admin = User.objects.create_user(
            phone='01710002003', name='Admin', password='Str0ngPass!23',
            role=User.Role.ADMIN, is_staff=True,
        )

        self.auth = self._auth(self.teacher_user)
        self.admin_auth = self._auth(self.admin)

        section = Section.objects.create(course=self.theirs, title='Week 1')
        self.their_content = Content.objects.create(
            course=self.theirs, section=section, title='Lesson', type=Content.Type.NOTE
        )

    def _auth(self, user):
        return {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=user).key}'}

    # -- the list --------------------------------------------------------
    def test_a_teacher_lists_only_their_own_courses(self):
        titles = [
            row['title']
            for row in self.client.get(f'{API}/admin/courses/', **self.auth).json()['data']
        ]
        self.assertEqual(titles, ['My Course'])

    def test_an_admin_still_lists_every_course(self):
        titles = {
            row['title']
            for row in self.client.get(f'{API}/admin/courses/', **self.admin_auth).json()['data']
        }
        self.assertEqual(titles, {'My Course', 'Their Course'})

    def test_a_teacher_lists_only_their_own_lessons(self):
        listed = self.client.get(f'{API}/admin/contents/', **self.auth).json()['data']
        self.assertEqual(listed, [])

    # -- the object ------------------------------------------------------
    def test_a_teacher_cannot_open_another_teachers_course(self):
        response = self.client.get(f'{API}/admin/courses/their-course/', **self.auth)
        self.assertIn(response.status_code, (403, 404))

    def test_a_teacher_can_open_their_own_course(self):
        response = self.client.get(f'{API}/admin/courses/my-course/', **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_teacher_cannot_edit_another_teachers_course(self):
        response = self.client.patch(
            f'{API}/admin/courses/their-course/', {'title': 'Hijacked'}, **self.auth
        )
        self.assertIn(response.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, 'Their Course')

    def test_a_teacher_cannot_toggle_another_teachers_lesson(self):
        """The toggle endpoint fetches its own row, so DRF never runs an
        object permission for it -- it has to ask explicitly."""
        was_active = self.their_content.active
        response = self.client.get(
            f'{API}/admin/contents/{self.their_content.pk}/toggle/?action=active',
            **self.auth,
        )
        self.assertEqual(response.status_code, 403)
        self.their_content.refresh_from_db()
        self.assertEqual(self.their_content.active, was_active)

    def test_a_teacher_cannot_read_another_courses_enrolments(self):
        response = self.client.get(
            f'{API}/admin/courses/{self.theirs.pk}/enrollments/', **self.auth
        )
        self.assertEqual(response.status_code, 403)

    def test_a_teacher_can_read_their_own_courses_enrolments(self):
        response = self.client.get(
            f'{API}/admin/courses/{self.mine.pk}/enrollments/', **self.auth
        )
        self.assertEqual(response.status_code, 200)

    # -- the link itself -------------------------------------------------
    def test_linking_a_login_reaches_assignments_made_earlier(self):
        """A teacher is usually put on their courses first and given a login
        later. Without the signal, those earlier assignments keep a null
        `user` -- which is exactly the set of courses they cannot open."""
        from apps.faculty.models import CourseInstructor, Teacher

        late = Teacher.objects.create(name='Late Starter')
        assignment = CourseInstructor.objects.create(
            teacher=late, course=self.theirs, name='Late Starter'
        )
        self.assertIsNone(assignment.user_id)

        late.user = User.objects.create_user(
            phone='01710002004', name='Late', role=User.Role.INSTRUCTOR
        )
        late.save()

        assignment.refresh_from_db()
        self.assertEqual(assignment.user_id, late.user_id)

    def test_a_new_assignment_inherits_the_teachers_login(self):
        from apps.faculty.models import CourseInstructor

        assignment = CourseInstructor.objects.create(
            teacher=self.teacher, course=self.theirs, name='Rahad'
        )
        self.assertEqual(assignment.user_id, self.teacher_user.pk)
