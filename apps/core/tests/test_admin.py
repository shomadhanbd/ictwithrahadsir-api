"""The Django admin has to actually render."""

from django.contrib import admin
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.core.testing import next_slug
from apps.identity.models import User

#: Apps whose admin is Django's own, not ours.
THIRD_PARTY_LABELS = {'auth', 'authtoken', 'contenttypes', 'sessions', 'admin'}

#: WhiteNoise's manifest storage needs `collectstatic`; the plain backend renders the same pages.
render_admin_templates = override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    }
)


def project_admins():
    for model, model_admin in admin.site._registry.items():
        if model._meta.app_label not in THIRD_PARTY_LABELS:
            yield model, model_admin


@render_admin_templates
class AdminSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            phone='01700000001', email='admin@example.com', password='Str0ngPass!23', name='Admin'
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_every_changelist_renders(self):
        for model, _ in project_admins():
            meta = model._meta
            with self.subTest(model=f'{meta.app_label}.{model.__name__}'):
                url = reverse(f'admin:{meta.app_label}_{meta.model_name}_changelist')
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_every_add_form_renders(self):
        """Catches a broken `fieldsets` or a bad `autocomplete_fields` target."""
        for model, model_admin in project_admins():
            meta = model._meta
            if not model_admin.has_add_permission(_FakeRequest(self.admin_user)):
                continue
            with self.subTest(model=f'{meta.app_label}.{model.__name__}'):
                url = reverse(f'admin:{meta.app_label}_{meta.model_name}_add')
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_search_renders_where_it_is_offered(self):
        for model, model_admin in project_admins():
            if not model_admin.search_fields:
                continue
            meta = model._meta
            with self.subTest(model=f'{meta.app_label}.{model.__name__}'):
                url = reverse(f'admin:{meta.app_label}_{meta.model_name}_changelist')
                self.assertEqual(self.client.get(url, {'q': 'a'}).status_code, 200)


class _FakeRequest:
    """Just enough request for `has_add_permission`."""

    def __init__(self, user):
        self.user = user


@render_admin_templates
class AdminQueryBudgetTests(TestCase):
    """A changelist's cost must not grow with the number of rows on it."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_superuser(
            phone='01700000002', email='admin2@example.com', password='Str0ngPass!23', name='Admin'
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def _queries_for(self, url):
        with CaptureQueriesContext(connection) as ctx:
            self.assertEqual(self.client.get(url).status_code, 200)
        return len(ctx)

    def _assert_flat(self, app_label, model_name, make_row):
        url = reverse(f'admin:{app_label}_{model_name}_changelist')
        make_row()
        baseline = self._queries_for(url)
        for _ in range(4):
            make_row()
        grown = self._queries_for(url)
        self.assertEqual(
            grown,
            baseline,
            f'{app_label}.{model_name} changelist ran {grown} queries for 5 rows and '
            f'{baseline} for 1 -- it is missing list_select_related.',
        )

    def test_enrollment_changelist_is_flat(self):
        from apps.courses.models import Course, Enrollment

        course = Course.objects.create(slug=next_slug("course"), title='ICT', status='published')
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            Enrollment.objects.create(
                course=course,
                user=User.objects.create_user(phone=f'0181070{i:04d}', name=f'S{i}'),
            )

        self._assert_flat('courses', 'enrollment', make_row)

    def test_payment_changelist_is_flat(self):
        from apps.billing.models import Payment, Product

        product = Product.objects.create(product_id=next_slug("product"), title='ICT', price=100, base_price=100)
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            user = User.objects.create_user(phone=f'0181080{i:04d}', name=f'B{i}')
            Payment.objects.create(user=user, product=product, amount=100)

        self._assert_flat('billing', 'payment', make_row)

    def test_content_changelist_is_flat(self):
        from apps.courses.models import Content, Course, Section

        course = Course.objects.create(slug=next_slug("course"), title='ICT', status='published')
        section = Section.objects.create(course=course, title='S1')
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            Content.objects.create(course=course, section=section, title=f'Lesson {i}')

        self._assert_flat('courses', 'content', make_row)
