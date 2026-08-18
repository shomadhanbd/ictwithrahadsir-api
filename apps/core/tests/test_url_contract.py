"""Guards the public URL surface against accidental drift.

Both frontends call this API by literal path, so any change to the set of
served URLs is a change they can see. The snapshot below makes that
deliberate rather than incidental: it fails on any addition or removal, and
is regenerated only when the change is intended.
"""

from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import Resolver404, resolve

from apps.core.url_contract import SNAPSHOT_PATH, current_url_contract


class RetiredPathTests(TestCase):
    """The original flat paths were carried for one release as deprecated
    aliases and have now been removed.

    Both halves matter: the old paths must be gone (so nothing quietly keeps
    depending on them) and every replacement must resolve (so the removal
    did not take a live route with it).
    """

    #: (retired path, canonical replacement)
    ALIASES = [
        ('/api/login', '/api/v1/auth/login/'),
        ('/api/register', '/api/v1/auth/register/'),
        ('/api/get-otp', '/api/v1/auth/otp/'),
        ('/api/verify-otp', '/api/v1/auth/otp/verify/'),
        ('/api/check-phone', '/api/v1/auth/phone-check/'),
        ('/api/forget-password', '/api/v1/auth/password/forgot/'),
        ('/api/password-reset', '/api/v1/auth/password/reset/'),
        ('/api/user', '/api/v1/me/'),
        ('/api/my-course', '/api/v1/me/courses/'),
        ('/api/courses', '/api/v1/courses/'),
        ('/api/course-category', '/api/v1/course-categories/'),
        ('/api/notices', '/api/v1/notices/'),
        ('/api/notice-category', '/api/v1/notice-categories/'),
        ('/api/products', '/api/v1/products/'),
        ('/api/home', '/api/v1/home/'),
        ('/api/contact-us', '/api/v1/contact-messages/'),
        ('/api/cart', '/api/v1/cart/'),
        ('/api/cart/add-remove', '/api/v1/cart/items/1/'),
        ('/api/order', '/api/v1/orders/'),
        ('/api/orders', '/api/v1/orders/'),
        ('/api/payment', '/api/v1/payments/'),
        ('/api/free-course-purchase', '/api/v1/enrollments/free/'),
        ('/api/aws-upload-url', '/api/v1/uploads/signed-url/'),
        ('/api/exams/1', '/api/v1/exams/1/'),
        ('/api/ranking/1', '/api/v1/exams/1/ranking/'),
        ('/api/admin/user', '/api/v1/admin/users/'),
        ('/api/admin/user-search', '/api/v1/admin/users/search/'),
        ('/api/admin/user/import', '/api/v1/admin/users/import/'),
        ('/api/admin/team', '/api/v1/admin/teachers/'),
        ('/api/admin/teacher', '/api/v1/admin/teachers/lookup/'),
        ('/api/admin/course', '/api/v1/admin/courses/'),
        ('/api/admin/course-category', '/api/v1/admin/course-categories/'),
        ('/api/admin/section', '/api/v1/admin/sections/'),
        ('/api/admin/content', '/api/v1/admin/contents/'),
        ('/api/admin/price', '/api/v1/admin/prices/'),
        ('/api/admin/coupon', '/api/v1/admin/coupons/'),
        ('/api/admin/routine', '/api/v1/admin/routines/'),
        ('/api/admin/instructor', '/api/v1/admin/instructors/'),
        ('/api/admin/mcq', '/api/v1/admin/mcq-questions/'),
        ('/api/admin/mcq-store', '/api/v1/admin/mcq-folders/'),
        ('/api/admin/result', '/api/v1/admin/exam-results/'),
        ('/api/admin/product', '/api/v1/admin/products/'),
        ('/api/admin/payment', '/api/v1/admin/payments/'),
        ('/api/admin/notice', '/api/v1/admin/notices/'),
        ('/api/admin/notice-category', '/api/v1/admin/notice-categories/'),
        ('/api/admin/testimonial', '/api/v1/admin/testimonials/'),
        ('/api/admin/advertisement', '/api/v1/admin/advertisements/'),
        ('/api/admin/exclusive-ebook', '/api/v1/admin/ebooks/'),
        ('/api/admin/page', '/api/v1/admin/pages/'),
        ('/api/admin/contact', '/api/v1/admin/contact-messages/'),
        ('/api/admin/course-materials', '/api/v1/admin/course-materials/'),
        ('/api/admin/dashboard', '/api/v1/admin/dashboard/'),
        ('/api/admin/sms-balance', '/api/v1/admin/sms-balance/'),
        ('/api/admin/logout', '/api/v1/admin/auth/logout/'),
    ]

    def test_every_retired_path_is_gone(self):
        for legacy, canonical in self.ALIASES:
            with self.subTest(path=legacy), self.assertRaises(
                Resolver404,
                msg=f'{legacy} still routes; it was replaced by {canonical}',
            ):
                resolve(legacy)

    def test_every_replacement_resolves(self):
        for legacy, canonical in self.ALIASES:
            with self.subTest(path=canonical):
                self.assertIsNotNone(
                    resolve(canonical), f'{canonical} (replacing {legacy}) does not route'
                )

    def test_the_stored_media_path_survived_the_removal(self):
        # Deliberately never versioned or deprecated: this path is baked into
        # absolute URLs already written into image and file columns, so
        # retiring it would orphan every previously uploaded file.
        self.assertIsNotNone(resolve('/api/media-upload/uploads/photo.png'))


class UrlContractTests(TestCase):
    def test_served_paths_match_the_snapshot(self):
        snapshot_file = Path(settings.BASE_DIR) / SNAPSHOT_PATH
        self.assertTrue(
            snapshot_file.exists(),
            f'{SNAPSHOT_PATH} is missing. Run: python manage.py dump_url_contract',
        )

        expected = snapshot_file.read_text().split()
        actual = current_url_contract()

        added = sorted(set(actual) - set(expected))
        removed = sorted(set(expected) - set(actual))

        self.assertEqual(
            (added, removed),
            ([], []),
            '\n\nThe set of served URLs changed.\n'
            f'  added:   {added or "none"}\n'
            f'  removed: {removed or "none"}\n\n'
            'Both frontends call these paths literally. If the change is\n'
            'intentional, run `python manage.py dump_url_contract` and\n'
            'review the diff; otherwise fix the routing regression.',
        )
