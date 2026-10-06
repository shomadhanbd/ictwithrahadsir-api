from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from apps.core.testing import bearer, make_user
from apps.courses.models import (
    Content,
    ContentCompletion,
    Course,
    Enrollment,
    Section,
)


class CourseProgressTests(APITestCase):
    def setUp(self):
        self.student = make_user()
        self.auth = bearer(self.student)
        self.course = Course.objects.create(title='ICT', slug='ict-progress', status='published')
        section = Section.objects.create(course=self.course, title='Ch1', slug='ict-progress-ch1')
        self.lessons = [
            Content.objects.create(
                course=self.course,
                section=section,
                title=f'Lesson {i}',
                slug=f'ict-progress-l{i}',
                type=Content.Type.VIDEO,
                active=True,
            )
            for i in range(4)
        ]

    def url(self, slug=None):
        return reverse('api:courses:course_progress', args=[slug or self.course.slug])

    def enrol(self, **kwargs):
        return Enrollment.objects.create(course=self.course, user=self.student, **kwargs)

    def test_an_anonymous_visitor_is_rejected(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)

    def test_a_student_without_an_enrolment_is_rejected(self):
        self.assertEqual(self.client.get(self.url(), **self.auth).status_code, 403)

    def test_an_expired_enrolment_is_rejected(self):
        self.enrol(valid_till=timezone.now() - timezone.timedelta(days=1))
        self.assertEqual(self.client.get(self.url(), **self.auth).status_code, 403)

    def test_a_fresh_enrolment_starts_at_zero(self):
        self.enrol()
        data = self.client.get(self.url(), **self.auth).data['data']
        self.assertEqual((data['completed'], data['total'], data['percent']), (0, 4, 0))

    def test_marking_a_lesson_advances_the_count(self):
        self.enrol()
        response = self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['completed'], 1)
        self.assertEqual(response.data['data']['percent'], 25)
        self.assertIn(self.lessons[0].pk, response.data['data']['completed_content_ids'])

    def test_marking_the_same_lesson_twice_counts_once(self):
        self.enrol()
        for _ in range(2):
            response = self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.data['data']['completed'], 1)

    def test_a_lesson_can_be_un_marked(self):
        self.enrol()
        self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        response = self.client.delete(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.data['data']['completed'], 0)

    def test_un_marking_needs_a_valid_content_id(self):
        self.enrol()
        self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        response = self.client.delete(self.url(), {'content_id': 'abc'}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_a_lesson_from_another_course_is_rejected(self):
        self.enrol()
        other = Course.objects.create(title='Other', slug='other-progress')
        other_section = Section.objects.create(course=other, title='Ch1', slug='other-progress-ch1')
        stranger = Content.objects.create(
            course=other,
            section=other_section,
            title='Nope',
            slug='other-progress-l0',
            type=Content.Type.VIDEO,
            active=True,
        )
        response = self.client.post(self.url(), {'content_id': stranger.pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)

    def test_adding_a_lesson_dilutes_the_percentage(self):
        """A course that gains content should not leave everyone at 100%."""
        self.enrol()
        for lesson in self.lessons:
            self.client.post(self.url(), {'content_id': lesson.pk}, format='json', **self.auth)
        self.assertEqual(self.client.get(self.url(), **self.auth).data['data']['percent'], 100)

        section = Section.objects.get(course=self.course)
        Content.objects.create(
            course=self.course,
            section=section,
            title='Lesson 5',
            slug='ict-progress-l5',
            type=Content.Type.VIDEO,
            active=True,
        )
        data = self.client.get(self.url(), **self.auth).data['data']
        self.assertEqual((data['completed'], data['total'], data['percent']), (4, 5, 80))

    def test_a_hidden_lesson_leaves_both_counts(self):
        self.enrol()
        for lesson in self.lessons:
            self.client.post(self.url(), {'content_id': lesson.pk}, format='json', **self.auth)
        Content.objects.filter(pk=self.lessons[0].pk).update(active=False)
        data = self.client.get(self.url(), **self.auth).data['data']
        self.assertEqual((data['completed'], data['total'], data['percent']), (3, 3, 100))

    def test_an_exam_lesson_cannot_be_ticked_by_hand(self):
        self.enrol()
        Content.objects.filter(pk=self.lessons[0].pk).update(type=Content.Type.EXAM)
        response = self.client.post(self.url(), {'content_id': self.lessons[0].pk}, format='json', **self.auth)
        self.assertEqual(response.status_code, 422)


class ContentCompletionRealignmentTests(APITestCase):
    """A lesson that changes course takes its completions with it."""

    def setUp(self):
        self.student = make_user()
        self.origin = Course.objects.create(title='Origin', slug='origin', status='published')
        self.destination = Course.objects.create(title='Destination', slug='destination', status='published')
        self.content = Content.objects.create(
            course=self.origin,
            section=Section.objects.create(course=self.origin, title='S1'),
            title='Lesson',
            active=True,
        )
        self.completion = ContentCompletion.objects.create(user=self.student, content=self.content, course=self.origin)

    def move_content(self):
        self.content.course = self.destination
        self.content.section = Section.objects.create(course=self.destination, title='S2')
        self.content.save()

    def test_moving_a_lesson_repoints_its_completions(self):
        self.move_content()
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.course_id, self.destination.pk)

    def test_progress_follows_the_lesson_to_its_new_course(self):
        from apps.courses.selectors import course_progress

        self.move_content()
        self.assertEqual(course_progress(user=self.student, course=self.destination)['completed'], 1)
        self.assertEqual(course_progress(user=self.student, course=self.origin)['completed'], 0)

    def test_saving_a_lesson_that_did_not_move_changes_nothing(self):
        self.content.title = 'Renamed'
        self.content.save()
        self.completion.refresh_from_db()
        self.assertEqual(self.completion.course_id, self.origin.pk)

    def test_other_lessons_completions_are_untouched(self):
        other = Content.objects.create(
            course=self.origin,
            section=self.content.section_id and self.content.section,
            title='Another',
            active=True,
        )
        other_completion = ContentCompletion.objects.create(user=self.student, content=other, course=self.origin)
        self.move_content()
        other_completion.refresh_from_db()
        self.assertEqual(other_completion.course_id, self.origin.pk)
