"""Guards against retired legacy paths quietly coming back."""

from django.test import TestCase
from django.urls import Resolver404, resolve


class RetiredPathTests(TestCase):
    """Old flat paths are gone and every replacement resolves."""

    #: (retired path, canonical replacement)
    ALIASES = [
        ('/api/login', '/api/public/auth/login/'),
        ('/api/register', '/api/public/auth/register/'),
        ('/api/get-otp', '/api/public/auth/otp/'),
        ('/api/verify-otp', '/api/public/auth/otp/verify/'),
        ('/api/forget-password', '/api/public/auth/password/forgot/'),
        ('/api/password-reset', '/api/public/auth/password/reset/'),
        ('/api/user', '/api/public/me/'),
        ('/api/my-course', '/api/public/me/courses/'),
        ('/api/courses', '/api/public/courses/'),
        ('/api/notices', '/api/public/notices/'),
        ('/api/notice-category', '/api/public/notice-categories/'),
        ('/api/home', '/api/public/home/'),
        ('/api/order', '/api/public/payments/initiate/'),
        ('/api/orders', '/api/public/me/payments/'),
        ('/api/payment', '/api/public/payments/initiate/'),
        ('/api/public/payments/', '/api/public/payments/initiate/'),
        ('/api/free-course-purchase', '/api/public/payments/initiate/'),
        ('/api/admin/user', '/api/private/users/'),
        ('/api/admin/user-search', '/api/private/users/search/'),
        ('/api/admin/team', '/api/private/teachers/'),
        ('/api/admin/teacher', '/api/private/teachers/lookup/'),
        ('/api/admin/course', '/api/private/courses/'),
        ('/api/admin/section', '/api/private/sections/'),
        ('/api/admin/content', '/api/private/contents/'),
        ('/api/admin/price', '/api/private/products/'),
        ('/api/admin/routine', '/api/private/routines/'),
        ('/api/admin/instructor', '/api/private/course-teachers/'),
        ('/api/admin/payment', '/api/private/payments/'),
        ('/api/admin/notice', '/api/private/notices/'),
        ('/api/admin/notice-category', '/api/private/notice-categories/'),
        ('/api/admin/testimonial', '/api/private/testimonials/'),
        ('/api/admin/advertisement', '/api/private/advertisements/'),
        ('/api/admin/exclusive-ebook', '/api/private/materials/topics/'),
        ('/api/admin/page', '/api/private/pages/'),
        ('/api/admin/sms-balance', '/api/private/sms-balance/'),
        ('/api/admin/logout', '/api/public/auth/logout/'),
    ]

    def test_every_retired_path_is_gone(self):
        for legacy, canonical in self.ALIASES:
            with (
                self.subTest(path=legacy),
                self.assertRaises(
                    Resolver404,
                    msg=f'{legacy} still routes; it was replaced by {canonical}',
                ),
            ):
                resolve(legacy)

    def test_every_replacement_resolves(self):
        for legacy, canonical in self.ALIASES:
            with self.subTest(path=canonical):
                self.assertIsNotNone(resolve(canonical), f'{canonical} (replacing {legacy}) does not route')
