from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.academic import curriculum
from apps.academic.models import ClassLevel, Group, Subject
from apps.academic.services import seed_curriculum

SUBJECT_TOTAL = sum(len(subjects) for by_group in curriculum.SUBJECTS.values() for subjects in by_group.values())


class SeedCurriculumTests(TestCase):
    def test_it_writes_every_level_group_and_subject(self):
        created = seed_curriculum()
        self.assertEqual(created, {"class levels": 2, "groups": 4, "subjects": SUBJECT_TOTAL})
        self.assertEqual(Subject.objects.count(), SUBJECT_TOTAL)

    def test_general_is_the_only_common_group(self):
        seed_curriculum()
        self.assertEqual(list(Group.objects.filter(is_common=True).values_list("slug", flat=True)), ["general"])

    def test_compulsory_subjects_sit_under_general(self):
        seed_curriculum()
        ict = Subject.objects.get(slug="ict-hsc-general")
        self.assertEqual((ict.class_level.slug, ict.group.slug), ("hsc", "general"))
        self.assertTrue(Subject.objects.filter(slug="physics-1st-hsc-science").exists())

    def test_running_it_again_adds_nothing(self):
        seed_curriculum()
        self.assertEqual(seed_curriculum(), {"class levels": 0, "groups": 0, "subjects": 0})
        self.assertEqual(Subject.objects.count(), SUBJECT_TOTAL)

    def test_it_keeps_what_staff_changed(self):
        seed_curriculum()
        ClassLevel.objects.filter(slug="ssc").update(name="SSC (renamed)")
        Subject.objects.filter(slug="math-ssc-general").update(is_active=False)
        seed_curriculum()
        self.assertEqual(ClassLevel.objects.get(slug="ssc").name, "SSC (renamed)")
        self.assertFalse(Subject.objects.get(slug="math-ssc-general").is_active)

    def test_the_command_runs(self):
        call_command("seed_curriculum", stdout=StringIO())
        self.assertEqual(Subject.objects.count(), SUBJECT_TOTAL)
