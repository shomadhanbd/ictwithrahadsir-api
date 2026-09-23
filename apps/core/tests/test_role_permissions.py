"""Which role may reach which admin endpoint.

There used to be one answer for the whole panel: `IsAdminRole` admitted
admins and teachers alike, on every `/admin/*` route and every method. A
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

API = '/api'

#: Admins only: accounts, money, pricing, and who teaches what.
FULL_ADMIN_ONLY = [
    f'{API}/private/payments/',
    f'{API}/private/dashboard/',
    f'{API}/private/dashboard/sales-overview/',
    f'{API}/private/dashboard/payment-chart/',
    f'{API}/private/prices/',
    f'{API}/private/coupons/',
    f'{API}/private/teachers/',
    f'{API}/private/course-teachers/',
    f'{API}/private/sms-balance/',
]

#: Admins write, teachers read. The academic taxonomy decides who a teacher is
#: and which class a student is in, so changing it stays a roster decision --
#: but a teacher naming a subject for an exam section, or filtering the
#: question bank by chapter, only ever reads it.
ADMIN_WRITE_TEACHER_READ = [
    f'{API}/private/subjects/',
    f'{API}/private/class-levels/',
    f'{API}/private/groups/',
    f'{API}/private/batches/',
    f'{API}/private/chapters/',
    f'{API}/private/topics/',
]

#: Its own case: admins manage anybody, teachers manage students only, and
#: moderators are kept out entirely. The collection is reachable by both
#: admins and teachers; who they may act *on* is object-level and lives in
#: `apps.identity.api.permissions.CanManageUsers` (tested there).
USER_MANAGEMENT = [
    f'{API}/private/users/',
]

#: Admins and moderators: the published site and the contact inbox.
CONTENT_STAFF = [
    f'{API}/private/notices/',
    f'{API}/private/notice-categories/',
    f'{API}/private/testimonials/',
    f'{API}/private/advertisements/',
    f'{API}/private/ebooks/',
    f'{API}/private/pages/',
]

#: Admins and teachers: courses and everything taught inside them.
TEACHING_STAFF = [
    f'{API}/private/courses/',
    f'{API}/private/course-categories/',
    f'{API}/private/sections/',
    f'{API}/private/contents/',
    f'{API}/private/course-materials/',
    f'{API}/private/routines/',
    # Minting a presigned upload URL is back-office write access to the
    # bucket, so it sits with the other teaching-staff tools.
    f'{API}/private/uploads/signed-url/',
    # The question bank and the exams built out of it: a teacher cannot
    # assemble a paper from questions they are not allowed to see.
    f'{API}/private/question-blocks/',
    f'{API}/private/questions/',
    f'{API}/private/question-sources/',
    f'{API}/private/question-types/',
    f'{API}/private/exams/',
    f'{API}/private/exam-sections/',
    f'{API}/private/exam-section-questions/',
    f'{API}/private/users/search/',
]


class RoleMatrixTests(ThrottledAPITestCase):
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
            self.tokens[role] = {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=user).key}'}

    def assert_reachable(self, paths, role, *, allowed):
        for path in paths:
            with self.subTest(role=role, path=path):
                status = self.client.get(path, **self.tokens[role]).status_code
                if allowed:
                    self.assertNotEqual(status, 403, f'{role} was refused {path}')
                else:
                    self.assertEqual(status, 403, f'{role} reached {path} (got {status})')

    # -- admin sees everything ------------------------------------------
    def test_admin_reaches_every_tier(self):
        for group in (
            FULL_ADMIN_ONLY,
            CONTENT_STAFF,
            TEACHING_STAFF,
            USER_MANAGEMENT,
            ADMIN_WRITE_TEACHER_READ,
        ):
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
        self.assert_reachable(TEACHING_STAFF, User.Role.TEACHER, allowed=True)

    def test_teacher_is_kept_out_of_accounts_and_money(self):
        """The headline regression: before the split, every one of these was
        open to any teacher."""
        self.assert_reachable(FULL_ADMIN_ONLY, User.Role.TEACHER, allowed=False)

    def test_teacher_reads_the_academic_taxonomy(self):
        """Without this every subject and chapter control in the exam builder
        comes back empty."""
        self.assert_reachable(ADMIN_WRITE_TEACHER_READ, User.Role.TEACHER, allowed=True)

    def test_teacher_cannot_change_the_academic_taxonomy(self):
        """Reading it is not managing it: what subjects exist is a roster
        decision, and the matrix only ever issues GETs."""
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
        self.assert_reachable(ADMIN_WRITE_TEACHER_READ, User.Role.MODERATOR, allowed=False)

    def test_teacher_is_kept_out_of_site_content(self):
        self.assert_reachable(CONTENT_STAFF, User.Role.TEACHER, allowed=False)

    def test_teacher_still_reaches_the_student_roster(self):
        """Deliberately not admin-only: a teacher enrols students on their own
        courses. What they may do to a given account is checked per object."""
        self.assert_reachable(USER_MANAGEMENT, User.Role.TEACHER, allowed=True)

    # -- student: none of it ---------------------------------------------
    def test_a_student_reaches_no_admin_endpoint(self):
        for group in (
            FULL_ADMIN_ONLY,
            CONTENT_STAFF,
            TEACHING_STAFF,
            USER_MANAGEMENT,
            ADMIN_WRITE_TEACHER_READ,
        ):
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
        'api/private/users/import/',
        'api/private/enrollments/',
        'api/private/teachers/lookup/',
    }

    def test_the_matrix_covers_every_admin_collection(self):
        listed = {
            p.removeprefix(f'{API}/')
            for p in FULL_ADMIN_ONLY + CONTENT_STAFF + TEACHING_STAFF + USER_MANAGEMENT + ADMIN_WRITE_TEACHER_READ
        }

        contract = (
            (__import__('pathlib').Path(__file__).resolve().parent.parent / 'url_contract.txt').read_text().split()
        )

        # One normal form for both shapes a router can produce: registered
        # with the prefix inline (`api/^private/notices/$`) or mounted under
        # `include('private/')` (`api/private/^notices/$`). Same route, and
        # the matrix writes it as `private/notices/` either way.
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


class TeacherCourseScopingTests(ThrottledAPITestCase):
    """A teacher's reach stops at the courses they actually teach.

    Being on a course's staff list and being allowed to edit that course were
    unrelated facts until `courses.CourseTeacher.user` was read for access.
    A teacher is an account now, so the assignment points straight at it --
    there is no roster row holding a copy of the link in between.

    Both halves are checked, because each leaves a hole the other closes: the
    queryset filter hides other courses from the *list*, and the object
    permission stops them being reached *by id* anyway.
    """

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
        # The roster entry is the account's profile, so there is no separate
        # person to link: holding one is what makes a user a teacher.
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
        return {'HTTP_AUTHORIZATION': f'Bearer {Token.objects.create(user=user).key}'}

    # -- the list --------------------------------------------------------
    def test_a_teacher_lists_only_their_own_courses(self):
        titles = [row['title'] for row in self.client.get(f'{API}/private/courses/', **self.auth).json()['data']]
        self.assertEqual(titles, ['My Course'])

    def test_an_admin_still_lists_every_course(self):
        titles = {row['title'] for row in self.client.get(f'{API}/private/courses/', **self.admin_auth).json()['data']}
        self.assertEqual(titles, {'My Course', 'Their Course'})

    def test_a_teacher_lists_only_their_own_lessons(self):
        listed = self.client.get(f'{API}/private/contents/', **self.auth).json()['data']
        self.assertEqual(listed, [])

    # -- the object ------------------------------------------------------
    def test_a_teacher_cannot_open_another_teachers_course(self):
        response = self.client.get(f'{API}/private/courses/their-course/', **self.auth)
        self.assertIn(response.status_code, (403, 404))

    def test_a_teacher_can_open_their_own_course(self):
        response = self.client.get(f'{API}/private/courses/my-course/', **self.auth)
        self.assertEqual(response.status_code, 200)

    def test_a_teacher_cannot_edit_another_teachers_course(self):
        response = self.client.patch(f'{API}/private/courses/their-course/', {'title': 'Hijacked'}, **self.auth)
        self.assertIn(response.status_code, (403, 404))
        self.theirs.refresh_from_db()
        self.assertEqual(self.theirs.title, 'Their Course')

    def test_a_teacher_cannot_toggle_another_teachers_lesson(self):
        """The toggle endpoint fetches its own row, so DRF never runs an
        object permission for it -- it has to ask explicitly."""
        was_active = self.their_content.active
        response = self.client.get(
            f'{API}/private/contents/{self.their_content.pk}/toggle/?action=active',
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

    # -- the link itself -------------------------------------------------
    def test_a_teacher_reaches_a_course_the_moment_they_are_assigned(self):
        """Nothing has to be pushed anywhere for access to follow.

        Access is read through the assignment's own `user` at request time, so
        it is right by construction. It used to need a `post_save` receiver to
        copy the teacher's login id down onto every assignment -- and one to
        back-fill the assignments made before the login existed, because those
        were exactly the courses the teacher could not open.
        """
        from apps.courses.models import CourseTeacher

        # 404 rather than 403: the scoping mixin filters the queryset, so an
        # unassigned course is not merely refused, it is not there.
        self.assertIn(
            self.client.get(f'{API}/private/courses/their-course/', **self.auth).status_code,
            (403, 404),
        )

        CourseTeacher.objects.create(user=self.teacher_user, course=self.theirs)

        self.assertEqual(self.client.get(f'{API}/private/courses/their-course/', **self.auth).status_code, 200)
