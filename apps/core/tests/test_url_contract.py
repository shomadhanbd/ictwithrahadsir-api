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
        ('/api/products', '/api/public/products/'),
        ('/api/home', '/api/public/home/'),
        ('/api/contact-us', '/api/public/contact-messages/'),
        ('/api/cart', '/api/public/cart/'),
        ('/api/cart/add-remove', '/api/public/cart/items/1/'),
        ('/api/order', '/api/public/orders/'),
        ('/api/orders', '/api/public/orders/'),
        ('/api/payment', '/api/public/payments/'),
        ('/api/free-course-purchase', '/api/public/enrollments/free/'),
        ('/api/aws-upload-url', '/api/private/uploads/signed-url/'),
        ('/api/exams/1', '/api/public/exams/1/'),
        ('/api/ranking/1', '/api/public/exams/1/ranking/'),
        ('/api/admin/user', '/api/private/users/'),
        ('/api/admin/user-search', '/api/private/users/search/'),
        ('/api/admin/user/import', '/api/private/users/import/'),
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
        ('/api/admin/mcq', '/api/private/mcq-questions/'),
        ('/api/admin/mcq-store', '/api/private/mcq-folders/'),
        ('/api/admin/result', '/api/private/exam-results/'),
        ('/api/admin/product', '/api/private/products/'),
        ('/api/admin/payment', '/api/private/payments/'),
        ('/api/admin/notice', '/api/private/notices/'),
        ('/api/admin/notice-category', '/api/private/notice-categories/'),
        ('/api/admin/testimonial', '/api/private/testimonials/'),
        ('/api/admin/advertisement', '/api/private/advertisements/'),
        ('/api/admin/exclusive-ebook', '/api/private/ebooks/'),
        ('/api/admin/page', '/api/private/pages/'),
        ('/api/admin/contact', '/api/private/contact-messages/'),
        ('/api/admin/course-materials', '/api/private/course-materials/'),
        ('/api/admin/dashboard', '/api/private/dashboard/'),
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
