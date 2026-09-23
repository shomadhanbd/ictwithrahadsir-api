from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.identity.models import OTP, User
from apps.profiles.models import StudentProfile

PHONE = "01810005555"


def backdate(otp, seconds):
    stale = timezone.now() - timezone.timedelta(seconds=seconds)
    OTP.objects.filter(pk=otp.pk).update(created_at=stale)
    otp.refresh_from_db()
    return otp


class OtpIssueTests(TestCase):
    def test_the_code_is_digits_of_the_configured_length(self):
        otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertEqual(len(otp.code), settings.OTP_LENGTH)
        self.assertTrue(otp.code.isdigit())

    def test_issuing_records_the_purpose(self):
        otp = OTP.issue(PHONE, OTP.Purpose.PASSWORD_RESET)
        self.assertEqual(otp.purpose, OTP.Purpose.PASSWORD_RESET)

    def test_a_fresh_code_is_usable(self):
        self.assertTrue(OTP.issue(PHONE, OTP.Purpose.VERIFY).is_usable)

    def test_repeated_issues_do_not_return_one_fixed_code(self):
        codes = {OTP.issue(PHONE, OTP.Purpose.VERIFY).code for _ in range(25)}
        self.assertGreater(len(codes), 20)


class OtpUsabilityTests(TestCase):
    def setUp(self):
        self.otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)

    def test_a_consumed_code_is_not_usable(self):
        self.otp.consumed_at = timezone.now()
        self.assertFalse(self.otp.is_usable)

    def test_a_code_at_the_attempt_cap_is_not_usable(self):
        self.otp.attempts = settings.OTP_MAX_ATTEMPTS
        self.assertFalse(self.otp.is_usable)

    def test_expiry_is_measured_from_when_the_code_was_issued(self):
        self.assertTrue(backdate(self.otp, settings.OTP_TTL_SECONDS - 5).is_usable)
        self.assertFalse(backdate(self.otp, settings.OTP_TTL_SECONDS + 5).is_usable)

    def test_an_expired_code_is_not_usable(self):
        self.assertFalse(backdate(self.otp, settings.OTP_TTL_SECONDS + 5).is_usable)


class OtpPurposeScopingTests(TestCase):
    def test_verify_reads_the_newest_code_for_that_purpose(self):
        OTP.issue(PHONE, OTP.Purpose.VERIFY)
        newest = OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertTrue(OTP.verify(PHONE, newest.code, OTP.Purpose.VERIFY))

    def test_a_reset_code_does_not_satisfy_a_verify(self):
        reset = OTP.issue(PHONE, OTP.Purpose.PASSWORD_RESET)
        OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertFalse(OTP.verify(PHONE, reset.code, OTP.Purpose.VERIFY))


class OtpVerifyTests(TestCase):
    def setUp(self):
        self.otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)

    def test_the_right_code_is_accepted_and_marked_consumed(self):
        self.assertTrue(OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY))
        self.otp.refresh_from_db()
        self.assertIsNotNone(self.otp.consumed_at)

    def test_a_code_cannot_be_spent_twice(self):
        OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY)
        self.assertFalse(OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY))

    def test_a_wrong_guess_is_counted_in_the_database(self):
        self.assertFalse(OTP.verify(PHONE, "000000", OTP.Purpose.VERIFY))
        self.otp.refresh_from_db()
        self.assertEqual(self.otp.attempts, 1)

    def test_every_wrong_guess_lands(self):
        for expected in range(1, 4):
            OTP.verify(PHONE, "000000", OTP.Purpose.VERIFY)
            self.otp.refresh_from_db()
            self.assertEqual(self.otp.attempts, expected)

    def test_the_code_dies_at_the_attempt_cap(self):
        for _ in range(settings.OTP_MAX_ATTEMPTS):
            OTP.verify(PHONE, "000000", OTP.Purpose.VERIFY)
        self.assertFalse(OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY))

    def test_an_expired_code_is_refused(self):
        backdate(self.otp, settings.OTP_TTL_SECONDS + 5)
        self.assertFalse(OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY))

    def test_a_missing_code_is_refused_rather_than_raising(self):
        self.assertFalse(OTP.verify(PHONE, None, OTP.Purpose.VERIFY))
        self.assertFalse(OTP.verify(PHONE, "", OTP.Purpose.VERIFY))

    def test_the_wrong_purpose_is_refused(self):
        self.assertFalse(OTP.verify(PHONE, self.otp.code, OTP.Purpose.PASSWORD_RESET))

    def test_the_wrong_purpose_does_not_burn_the_real_code(self):
        OTP.verify(PHONE, self.otp.code, OTP.Purpose.PASSWORD_RESET)
        self.otp.refresh_from_db()
        self.assertEqual(self.otp.attempts, 0)
        self.assertTrue(OTP.verify(PHONE, self.otp.code, OTP.Purpose.VERIFY))


class OtpResendCooldownTests(TestCase):
    def test_no_wait_for_a_number_that_has_never_asked(self):
        self.assertEqual(OTP.seconds_until_resend(PHONE), 0)

    def test_a_fresh_code_starts_the_cooldown(self):
        OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertGreater(OTP.seconds_until_resend(PHONE), 0)

    def test_the_cooldown_lapses(self):
        otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)
        backdate(otp, settings.OTP_RESEND_COOLDOWN_SECONDS + 1)
        self.assertEqual(OTP.seconds_until_resend(PHONE), 0)

    def test_the_cooldown_is_shared_across_purposes(self):
        OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertGreater(OTP.seconds_until_resend(PHONE), 0)


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

    def test_a_deliberate_account_counts_as_registered(self):
        user = User.objects.create_user(phone=PHONE, name="Student")
        self.assertIn(user, User.objects.registered())

    def test_an_account_made_without_a_password_cannot_sign_in_with_one(self):
        user = User.objects.create_user(phone=PHONE, name="Student")
        self.assertFalse(user.has_usable_password())


class UserManagerPlaceholderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_unverified("+8801810002222")

    def test_a_placeholder_is_not_registered(self):
        self.assertNotIn(self.user, User.objects.registered())

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
        """It used to be a settable column that could disagree with the role.

        Passing it is now ignored rather than honoured, so nobody can make an
        admin account that is locked out of the Django admin site.
        """
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

    def test_registered_excludes_abandoned_sign_ups(self):
        registered = User.objects.registered()
        self.assertIn(self.student, registered)
        self.assertNotIn(self.placeholder, registered)

    def test_students_excludes_other_roles_and_placeholders(self):
        students = User.objects.students()
        self.assertEqual(list(students), [self.student])

    def test_joined_since_filters_on_date_joined(self):
        cutoff = timezone.now() - timezone.timedelta(days=1)
        self.assertEqual(User.objects.students().joined_since(cutoff).count(), 1)

        future = timezone.now() + timezone.timedelta(days=1)
        self.assertEqual(User.objects.students().joined_since(future).count(), 0)


class OtpStorageTests(TestCase):
    def test_the_code_survives_a_field_refresh(self):
        otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)
        code = otp.code
        otp.refresh_from_db()
        self.assertEqual(otp.code, code)

    def test_meta_is_recorded_when_given(self):
        otp = OTP.issue(PHONE, OTP.Purpose.VERIFY, meta={"platform": "android"})
        self.assertEqual(OTP.objects.get(pk=otp.pk).meta, {"platform": "android"})

    def test_meta_defaults_to_an_empty_dict(self):
        otp = OTP.issue(PHONE, OTP.Purpose.VERIFY)
        self.assertEqual(OTP.objects.get(pk=otp.pk).meta, {})


class RoleGroupPermissionTests(TestCase):
    """`is_staff` follows role, so a back-office group must carry permissions
    or its members reach the Django admin and find it empty."""

    def group(self, role):
        return Group.objects.get(name=role)

    def test_the_admin_group_holds_every_permission(self):
        self.assertEqual(self.group(User.Role.ADMIN).permissions.count(), Permission.objects.count())

    def test_the_moderator_group_is_scoped_to_the_published_site(self):
        labels = {p.content_type.app_label for p in self.group(User.Role.MODERATOR).permissions.all()}
        self.assertEqual(labels, {"content"})

    def test_a_moderator_can_actually_open_something_in_the_admin(self):
        moderator = User.objects.create_user(phone=PHONE, name="Mod", role=User.Role.MODERATOR)
        self.assertTrue(moderator.is_staff)
        self.assertTrue(moderator.has_perm("content.change_notice"))
        self.assertFalse(moderator.has_perm("billing.change_order"))

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
    """`identity` no longer owns the model, but `user.student` is still the way
    every serializer reaches it, so the accessor stays pinned from here."""

    def setUp(self):
        self.user = User.objects.create_user(phone=PHONE, name="Student")

    def test_it_is_reached_from_the_user_as_student(self):
        profile = StudentProfile.objects.create(user=self.user, institution="Dhaka College")
        self.user.refresh_from_db()
        self.assertEqual(self.user.student, profile)

    def test_a_user_without_one_simply_has_no_row(self):
        self.assertIsNone(getattr(self.user, "student", None))
