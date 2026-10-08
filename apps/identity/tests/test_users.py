"""The user model and manager: creating accounts, roles, and the role groups' permissions."""

from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.identity.models import User
from apps.profiles.models import StudentProfile

PHONE = "01810005555"


class UserManagerCreateTests(TestCase):
    def test_an_account_needs_a_phone(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(name="Nobody")

    def test_an_email_is_not_enough_on_its_own(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="solo@example.com", name="Nobody")

    def test_a_phone_that_normalises_to_nothing_is_rejected(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(phone="n/a", name="Nobody")

    def test_the_phone_is_stored_canonically(self):
        user = User.objects.create_user(phone="+8801810001111", name="Student")
        self.assertEqual(user.phone, "01810001111")

    def test_the_email_is_stored_lowercased(self):
        user = User.objects.create_user(phone=PHONE, email="Ali@Example.COM", name="Student")
        self.assertEqual(user.email, "ali@example.com")

    def test_a_new_account_defaults_to_the_student_role(self):
        user = User.objects.create_user(phone=PHONE, name="Student")
        self.assertEqual(user.role, User.Role.STUDENT)

    def test_an_account_made_without_a_password_cannot_sign_in_with_one(self):
        user = User.objects.create_user(phone=PHONE, name="Student")
        self.assertFalse(user.has_usable_password())


class UserManagerPlaceholderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_unverified("+8801810002222")

    def test_a_placeholder_is_a_student_with_a_canonical_phone(self):
        self.assertEqual(self.user.role, User.Role.STUDENT)
        self.assertEqual(self.user.phone, "01810002222")

    def test_a_placeholder_has_no_usable_password(self):
        self.assertFalse(self.user.has_usable_password())


class UserManagerSuperuserTests(TestCase):
    def test_a_superuser_gets_the_admin_role_and_both_flags(self):
        admin = User.objects.create_superuser(phone=PHONE, password="Str0ngPass!23")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_is_staff_cannot_be_turned_off_because_it_is_derived(self):
        admin = User.objects.create_superuser(phone=PHONE, password="x", is_staff=False)
        self.assertTrue(admin.is_staff)


class DerivedStaffTests(TestCase):
    """`is_staff` follows role, and nothing else can set it."""

    def test_back_office_roles_reach_the_admin_site(self):
        for role in (User.Role.ADMIN, User.Role.MODERATOR):
            with self.subTest(role=role):
                user = User.objects.create_user(phone="0181000" + str(1000 + list(User.Role).index(role)), role=role)
                self.assertTrue(user.is_staff)

    def test_teaching_and_learning_roles_do_not(self):
        for phone, role in (("01810002001", User.Role.TEACHER), ("01810002002", User.Role.STUDENT)):
            with self.subTest(role=role):
                self.assertFalse(User.objects.create_user(phone=phone, role=role).is_staff)

    def test_setting_a_role_replaces_the_previous_one(self):
        user = User.objects.create_user(phone=PHONE, role=User.Role.STUDENT)
        user.set_role(User.Role.ADMIN)

        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(
            list(user.groups.filter(name__in=User.Role.values).values_list("name", flat=True)),
            [User.Role.ADMIN],
        )

    def test_has_role_answers_for_the_current_group(self):
        user = User.objects.create_user(phone=PHONE, role=User.Role.TEACHER)
        self.assertTrue(user.has_role(User.Role.ADMIN, User.Role.TEACHER))
        self.assertFalse(user.has_role(User.Role.ADMIN, User.Role.MODERATOR))


class UserSaveNormalisationTests(TestCase):
    def test_a_direct_assignment_is_normalised_too(self):
        user = User.objects.create_user(phone="01810001111", name="Student")
        user.phone = "+880 1810-001111"
        user.email = "Mixed@Case.COM"
        user.save()

        user.refresh_from_db()
        self.assertEqual(user.phone, "01810001111")
        self.assertEqual(user.email, "mixed@case.com")


class UserConstraintTests(TestCase):
    def test_a_re_spelt_phone_is_the_same_account(self):
        User.objects.create_user(phone="01810001111", name="First")
        with self.assertRaises(IntegrityError), transaction.atomic():
            User.objects.create_user(phone="+8801810001111", name="Second")


class UserStrTests(TestCase):
    def test_it_prefers_the_name(self):
        user = User.objects.create_user(phone=PHONE, name="Rahim Uddin")
        self.assertEqual(str(user), "Rahim Uddin")

    def test_it_falls_back_to_the_phone(self):
        user = User.objects.create_user(phone=PHONE)
        self.assertEqual(str(user), PHONE)


class UserQuerySetTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(phone="01810001111", name="Student")
        self.teacher = User.objects.create_user(phone="01810002222", name="Teacher", role=User.Role.TEACHER)
        self.placeholder = User.objects.create_unverified("01810003333")

    def test_students_excludes_other_roles(self):
        students = User.objects.students()
        self.assertCountEqual(students, [self.student, self.placeholder])


class RoleGroupPermissionTests(TestCase):
    """Every back-office group carries Django admin permissions."""

    def group(self, role):
        return Group.objects.get(name=role)

    def test_the_admin_group_holds_every_permission(self):
        self.assertEqual(self.group(User.Role.ADMIN).permissions.count(), Permission.objects.count())

    def test_the_moderator_group_is_scoped_to_the_published_site(self):
        models = {
            (p.content_type.app_label, p.content_type.model) for p in self.group(User.Role.MODERATOR).permissions.all()
        }
        self.assertEqual({label for label, _ in models}, {"content", "communication"})
        self.assertNotIn(("communication", "smsmessage"), models)

    def test_a_moderator_can_actually_open_something_in_the_admin(self):
        moderator = User.objects.create_user(phone=PHONE, name="Mod", role=User.Role.MODERATOR)
        self.assertTrue(moderator.is_staff)
        self.assertTrue(moderator.has_perm("communication.change_notice"))
        self.assertFalse(moderator.has_perm("billing.change_payment"))

    def test_roles_that_never_reach_the_admin_get_nothing(self):
        for role in (User.Role.TEACHER, User.Role.STUDENT):
            with self.subTest(role=role):
                self.assertEqual(self.group(role).permissions.count(), 0)


class UserIndexTests(TestCase):
    def test_the_ordering_column_is_indexed(self):
        indexed = {tuple(index.fields) for index in User._meta.indexes}
        self.assertIn(("-date_joined",), indexed)
        self.assertEqual(User._meta.ordering, ["-date_joined"])


class StudentProfileTests(TestCase):
    """`user.student` reaches the student profile."""

    def setUp(self):
        self.user = User.objects.create_user(phone=PHONE, name="Student")

    def test_it_is_reached_from_the_user_as_student(self):
        profile = StudentProfile.objects.create(user=self.user, institution="Dhaka College")
        self.user.refresh_from_db()
        self.assertEqual(self.user.student, profile)

    def test_a_user_without_one_simply_has_no_row(self):
        self.assertIsNone(getattr(self.user, "student", None))
