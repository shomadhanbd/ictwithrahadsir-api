"""Guards against retired legacy paths quietly coming back."""

from django.test import TestCase
from django.urls import Resolver404, resolve


class RetiredPathTests(TestCase):
    """The original flat paths were carried for one release as deprecated
    aliases and have now been removed.

    Both halves matter: the old paths must be gone (so nothing quietly keeps
    depending on them) and every replacement must resolve (so the removal
    did not take a live route with it).
    """

    #: (retired path, canonical replacement)
    #:
    #: The exam-taking and MCQ-store aliases are gone with the `assessment`
    #: app they pointed into. They belong back here, aimed at the new routes,
    #: once `apps.exam` can serve a paper to a student.
    ALIASES = [
        ('/api/login', '/api/public/auth/login/'),
        ('/api/register', '/api/public/auth/register/'),
        ('/api/get-otp', '/api/public/auth/otp/'),
        ('/api/verify-otp', '/api/public/auth/otp/verify/'),
        ('/api/check-phone', '/api/public/auth/phone-check/'),
        ('/api/forget-password', '/api/public/auth/password/forgot/'),
        ('/api/password-reset', '/api/public/auth/password/reset/'),
        ('/api/user', '/api/public/me/'),
        ('/api/my-course', '/api/public/me/courses/'),
        ('/api/courses', '/api/public/courses/'),
        ('/api/course-category', '/api/public/course-categories/'),
        ('/api/notices', '/api/public/notices/'),
        ('/api/notice-category', '/api/public/notice-categories/'),
        ('/api/home', '/api/public/home/'),
        ('/api/order', '/api/public/orders/'),
        ('/api/orders', '/api/public/orders/'),
        # The manual transfer form went with the move to SSLCommerz; paying an
        # order is now `orders/<id>/pay/`.
        ('/api/payment', '/api/public/orders/1/pay/'),
        ('/api/public/payments/', '/api/public/orders/1/pay/'),
        ('/api/free-course-purchase', '/api/public/enrollments/free/'),
        ('/api/admin/user', '/api/private/users/'),
        ('/api/admin/user-search', '/api/private/users/search/'),
        ('/api/admin/team', '/api/private/teachers/'),
        ('/api/admin/teacher', '/api/private/teachers/lookup/'),
        ('/api/admin/course', '/api/private/courses/'),
        ('/api/admin/course-category', '/api/private/course-categories/'),
        ('/api/admin/section', '/api/private/sections/'),
        ('/api/admin/content', '/api/private/contents/'),
        ('/api/admin/price', '/api/private/prices/'),
        ('/api/admin/coupon', '/api/private/coupons/'),
        ('/api/admin/routine', '/api/private/routines/'),
        ('/api/admin/instructor', '/api/private/course-teachers/'),
        ('/api/admin/payment', '/api/private/payments/'),
        ('/api/admin/notice', '/api/private/notices/'),
        ('/api/admin/notice-category', '/api/private/notice-categories/'),
        ('/api/admin/testimonial', '/api/private/testimonials/'),
        ('/api/admin/advertisement', '/api/private/advertisements/'),
        ('/api/admin/exclusive-ebook', '/api/private/ebooks/'),
        ('/api/admin/page', '/api/private/pages/'),
        ('/api/admin/course-materials', '/api/private/course-materials/'),
        ('/api/admin/sms-balance', '/api/private/sms-balance/'),
        # The back-office signs out through the one logout endpoint now;
        # the separate admin alias was the same view and has been removed.
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
