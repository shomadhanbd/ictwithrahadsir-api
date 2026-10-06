import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock, skipUnless

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, override_settings

from apps.core.testing import make_user
from apps.courses.models import Course
from apps.identity.models import User


@skipUnless(apps.is_installed("apps.demo"), "seed_demo is installed by the local settings only")
class SeedDemoTests(TestCase):
    def setUp(self):
        # Each test states its own database and opt-in, so the outcome does not depend on where it runs.
        self.enterContext(mock.patch.dict(os.environ, {"ALLOW_DEMO_SEED": ""}))
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.enterContext(override_settings(MEDIA_ROOT=Path(media.name)))

    def seed(self, *args):
        call_command("seed_demo", *args, stdout=StringIO())

    def test_it_refuses_to_run_without_debug(self):
        Course.objects.create(title="Real course", slug="real")
        with self.assertRaises(CommandError) as refused:
            self.seed("--fresh")
        self.assertIn("DEBUG", str(refused.exception))
        self.assertTrue(Course.objects.filter(slug="real").exists())

    @override_settings(DEBUG=True)
    def test_it_refuses_a_real_database_even_with_debug_on(self):
        """manage.py falls back to the local settings, so DEBUG is on even on the production host."""
        Course.objects.create(title="Real course", slug="real")
        with mock.patch.object(connection, "vendor", "postgresql"), self.assertRaises(CommandError) as refused:
            self.seed("--fresh")
        self.assertIn("ALLOW_DEMO_SEED", str(refused.exception))
        self.assertTrue(Course.objects.filter(slug="real").exists())

    @override_settings(DEBUG=True)
    @mock.patch.object(connection, "vendor", "sqlite")
    def test_fresh_removes_only_the_accounts_it_minted(self):
        """0181 and 0171 are real operators' ranges, so a real customer there must survive."""
        real_student = make_user(phone="01810009999", name="Real Robi customer")
        real_teacher = make_user(role=User.Role.TEACHER, phone="01710009999", name="Real GP teacher")
        self.seed()
        self.seed("--fresh")
        self.assertTrue(User.objects.filter(pk__in=[real_student.pk, real_teacher.pk]).count() == 2)
        self.assertTrue(User.objects.filter(phone="01810000001").exists())


class SeedDemoInstallTests(TestCase):
    def test_production_does_not_install_the_demo_app(self):
        from apps.core.tests.test_production_settings import load_production

        self.assertNotIn("apps.demo", load_production().INSTALLED_APPS)
