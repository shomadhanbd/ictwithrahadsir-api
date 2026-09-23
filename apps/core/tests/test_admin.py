"""The Django admin has to actually render.

`manage.py check` validates the *configuration* -- that a field named in
`list_display` exists, that an `autocomplete_fields` target declares
`search_fields`. It says nothing about whether a custom column raises when it
is called with a real row, which is where admin mistakes usually live.

So these load every registered changelist and every add form for real, and
then assert the thing that actually degrades in production: that a changelist
does not run more queries as rows are added to it.
"""

from django.contrib import admin
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.identity.models import User

#: Apps whose admin is Django's own, not ours.
THIRD_PARTY_LABELS = {'auth', 'authtoken', 'contenttypes', 'sessions', 'admin'}

#: The admin templates resolve `{% static %}` for their own CSS. Production
#: serves that through WhiteNoise's *manifest* storage, which raises unless
#: `collectstatic` has been run -- a build step, not something a test should
#: need. The plain backend renders the same pages.
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
    """A changelist's cost must not grow with the number of rows on it.

    Every one of these lists renders at least one foreign key, so without
    `list_select_related` each row costs an extra query. The failure is
    invisible on seed data and makes the page unusable on real data, which is
    exactly the kind of regression a test should hold.
    """

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

        course = Course.objects.create(title='ICT', active=True)
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            Enrollment.objects.create(
                course=course,
                user=User.objects.create_user(phone=f'0181070{i:04d}', name=f'S{i}'),
            )

        self._assert_flat('courses', 'enrollment', make_row)

    def test_payment_changelist_is_flat(self):
        from decimal import Decimal

        from apps.billing.models import Order, Payment
        from apps.courses.models import Course

        course = Course.objects.create(title='ICT', active=True)
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            user = User.objects.create_user(phone=f'0181080{i:04d}', name=f'B{i}')
            order = Order.objects.create(user=user, course=course, amount=Decimal('100'), total=Decimal('100'))
            Payment.objects.create(order=order, amount=Decimal('100'), transaction_id=f'TRX{i}')

        self._assert_flat('billing', 'payment', make_row)

    def test_content_changelist_is_flat(self):
        from apps.courses.models import Content, Course, Section

        course = Course.objects.create(title='ICT', active=True)
        section = Section.objects.create(course=course, title='S1')
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            Content.objects.create(course=course, section=section, title=f'Lesson {i}')

        self._assert_flat('courses', 'content', make_row)

    def test_exam_attempt_changelist_is_flat(self):
        """Two levels deep (`exam__content`), which Django cannot infer.

        Django auto-applies a bare `select_related()` when `list_display`
        names a foreign key, which covers the one-level cases on its own.
        What it cannot do is follow a second hop, and both this list and the
        payment list render one -- so these are the two that genuinely need
        `list_select_related` spelled out.
        """
        from decimal import Decimal

        from apps.assessment.models import Exam, ExamAttempt
        from apps.courses.models import Content, Course, Section

        course = Course.objects.create(title='ICT', active=True)
        section = Section.objects.create(course=course, title='S1')
        content = Content.objects.create(course=course, section=section, title='Exam', type=Content.Type.EXAM)
        exam = Exam.objects.create(content=content)
        counter = iter(range(1000))

        def make_row():
            i = next(counter)
            ExamAttempt.objects.create(
                exam=exam,
                user=User.objects.create_user(phone=f'0181090{i:04d}', name=f'A{i}'),
                marks=Decimal('10'),
            )

        self._assert_flat('assessment', 'examattempt', make_row)
