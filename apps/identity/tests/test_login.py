from apps.core.tests.base import ThrottledAPITestCase
from apps.identity.models import User
from apps.identity.tests.base import (
    LOGIN_URL,
    REGISTER_URL,
)


class LoginTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            phone="01810002222",
            email="s@example.com",
            name="Student",
            password="Str0ngPass!23",
        )

    def test_login_with_phone(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["token"])
        self.assertEqual(response.json()["user"]["phone"], self.user.phone)

    def test_email_is_no_longer_a_login(self):
        """Phone is the only identifier.

        An account may still hold an email address; it is just not something
        you can sign in with.
        """
        response = self.client.post(
            LOGIN_URL,
            {"email": "s@example.com", "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 422)

    def test_login_requires_a_phone(self):
        response = self.client.post(LOGIN_URL, {"password": "x"})
        self.assertEqual(response.status_code, 422)

    def test_login_rejects_bad_password(self):
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "wrong"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertIn("password", response.json()["errors"])

    def test_login_rejects_inactive_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            LOGIN_URL,
            {"phone": self.user.phone, "password": "Str0ngPass!23"},
        )
        self.assertEqual(response.status_code, 422)


class LoginThrottleTests(ThrottledAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(phone='01810005555', name='Victim', password='Str0ngPass!23')

    def guess(self, password='wrong'):
        return self.client.post(LOGIN_URL, {'phone': self.user.phone, 'password': password}, format='json')

    def test_repeated_password_guesses_are_eventually_throttled(self):
        statuses = [self.guess().status_code for _ in range(15)]
        self.assertIn(429, statuses, f'no throttle fired: {statuses}')

    def test_the_throttle_also_stops_a_correct_password(self):
        for _ in range(15):
            self.guess()
        self.assertEqual(self.guess('Str0ngPass!23').status_code, 429)

    def test_the_limit_is_not_hit_by_ordinary_use(self):
        for _ in range(5):
            self.assertEqual(self.guess().status_code, 422)
        self.assertEqual(self.guess('Str0ngPass!23').status_code, 200)

    def test_the_throttled_response_keeps_the_error_envelope(self):
        for _ in range(15):
            self.guess()
        body = self.guess().json()
        self.assertIn('message', body)


class RegistrationThrottleTests(ThrottledAPITestCase):
    def test_registration_cannot_be_spammed_without_verified_sessions(self):
        statuses = []
        for i in range(15):
            response = self.client.post(
                REGISTER_URL,
                {
                    'name': 'Spam',
                    'phone': f'018100600{i:02d}',
                    'password': 'Str0ngPass!23',
                    'password_confirmation': 'Str0ngPass!23',
                },
                format='json',
            )
            statuses.append(response.status_code)
        self.assertEqual(set(statuses), {401}, f'unauthenticated register got through: {statuses}')
